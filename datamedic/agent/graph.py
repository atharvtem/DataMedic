"""Deterministic graph controls enforce budget, availability and termination."""
import time
import inspect
import asyncio
from datetime import date, timedelta
from decimal import Decimal
from pydantic import ValidationError
from langgraph.graph import StateGraph, START, END
from datamedic.agent.models import Alert, Hypothesis, Report, State, ToolRequest
from datamedic.agent.planner import COSTS, SERVERS, DeterministicPlanner


def assess(state):
    hypotheses = [Hypothesis.model_validate(h) for h in state['hypotheses']]
    good = {h['tool']:h for h in state['history'] if h['result'].get('ok') is True}
    refs = [h['id'] for h in good.values()]
    supported = False
    reason = 'Evidence is incomplete or conflicting.'
    try:
        coverage = good['check_payment_coverage']['result']
        rows = [dict(zip(coverage['columns'],r)) for r in coverage['rows']]
        day = state['alert']['purchase_date']
        end = (date.fromisoformat(day)+timedelta(days=1)).isoformat()
        target = next(r for r in rows if r['purchase_date']==day)
        prior = [r for r in rows if r['purchase_date']<day]
        drop = (len(prior)==7 and all(int(r['orders'])>0 for r in prior)
                and Decimal(target['paid_orders'])/Decimal(target['orders']) <
                sum(Decimal(r['paid_orders'])/Decimal(r['orders']) for r in prior)/7)
        if drop and int(target['missing_payment_orders'])>0:
            missing = next(h for h in hypotheses if h.category=='MISSING_INGESTION')
            missing.status='SUPPORTED'
            missing.rationale='Coverage fell against all seven reference days; ingestion cause still needs corroboration.'
            missing.evidence=[good['check_payment_coverage']['id']]
        def matching(tool):
            records = good[tool]['result']['records']
            return [r for r in records if r['details'].get('window_start')==day+'T00:00:00'
                    and r['details'].get('window_end')==end+'T00:00:00']
        etl = matching('query_etl_pipeline_logs')
        payments = [r['details'] for r in etl if r['details'].get('job')=='payments_import']
        orders = [r['details'] for r in etl if r['details'].get('job')=='orders_import']
        service = matching('check_upstream_service_events')
        config = matching('inspect_config_deployments')
        p,o = payments[0],orders[0]
        corroborated = (len(payments)==len(orders)==1 and p['status']=='FAILED' and p['exit_code']!=0
            and int(p['actual_rows'])==int(target['payment_rows'])
            and int(p['expected_rows'])-int(p['actual_rows']) >= int(target['missing_payment_orders']) > 0
            and o['status']=='SUCCESS' and int(o['expected_rows'])==int(o['actual_rows'])==int(target['orders']))
        healthy = bool(service) and all(r['details'].get('status')=='HEALTHY' and r['details'].get('error_count')==0 for r in service)
        unchanged = bool(config) and all(r['details'].get('status')=='UNCHANGED' for r in config)
        schema = good['inspect_database_schema']['result']['rows']
        schema_ok = {'order_id','order_purchase_timestamp'} <= {r[1] for r in schema if r[0]=='orders'}
        supported = bool(drop and corroborated and healthy and unchanged and schema_ok)
        if supported:
            reason='Reduced payment coverage aligns with a failed payment import and matching observed row count; order ingestion succeeded and matching service/configuration records provide no competing incident signal.'
            for h in hypotheses:
                h.status='SUPPORTED' if h.category=='MISSING_INGESTION' else 'WEAKENED'
                h.rationale=reason if h.status=='SUPPORTED' else 'Observed ingestion failure explains the missing coverage; available service/configuration evidence does not support this alternative. Not conclusively ruled out.'
                h.evidence=refs
    except (KeyError, ValueError, TypeError, StopIteration, IndexError, ArithmeticError):
        pass
    return [h.model_dump() for h in hypotheses], supported, reason, refs


def build_graph(transport, planner=None):
    planner = planner or DeterministicPlanner()
    async def initialize(state):
        try:
            raw = planner.hypotheses(state['alert'])
            raw = await asyncio.wait_for(raw, timeout=60) if inspect.isawaitable(raw) else raw
            hypotheses = [Hypothesis.model_validate(h).model_dump() for h in raw]
            if len(hypotheses) != 4 or {h['category'] for h in hypotheses} != {'MISSING_INGESTION','SILENT_LOGIC_CORRUPTION','UPSTREAM_SERVICE_OUTAGE','DUPLICATE_RECORDS'}:
                raise ValueError('Expected four hypotheses')
            return {'hypotheses':hypotheses}
        except (ValidationError, ValueError, TypeError, RuntimeError, TimeoutError):
            return {'hypotheses':[], 'stop':'INVALID_PLANNER_OUTPUT'}
    async def plan(state):
        if state['stop']:
            return {'request':None}
        try:
            raw = planner.next(state)
            raw = await asyncio.wait_for(raw, timeout=60) if inspect.isawaitable(raw) else raw
            if raw is None:
                return {'request':None,'stop':'NO_USEFUL_TOOL'}
            request = ToolRequest.model_validate(raw)
        except (ValidationError, ValueError, TypeError, RuntimeError, TimeoutError):
            return {'request':None,'stop':'INVALID_PLANNER_OUTPUT'}
        if request.tool not in COSTS:
            return {'request':None,'stop':'TOOL_UNAVAILABLE'}
        if sum(h['tool']==request.tool for h in state['history']) >= 2:
            return {'request':None,'stop':'RETRY_LIMIT'}
        if COSTS[request.tool] > state['remaining']:
            return {'request':None,'stop':'BUDGET_EXHAUSTED'}
        return {'request':request.model_dump()}
    async def call(state):
        request=ToolRequest.model_validate(state['request'])
        cost=COSTS[request.tool]
        started=time.monotonic()
        try:
            result=await transport.call(SERVERS[request.tool],request.tool,request.arguments)
            if not isinstance(result,dict) or not isinstance(result.get('ok'),bool):
                result={'ok':False,'code':'INVALID_TOOL_RESULT'}
        except Exception:
            result={'ok':False,'code':'TOOL_ERROR'}
        entry={'id':f"E{len(state['history'])+1}",'tool':request.tool,'arguments':request.arguments,
               'cost':cost,'elapsed_ms':round((time.monotonic()-started)*1000,2),'result':result}
        return {'remaining':state['remaining']-cost,'history':state['history']+[entry]}
    def evaluate(state):
        hypotheses,supported,_,_=assess(state)
        history = state['history'][:-1]+[{**state['history'][-1], 'hypotheses_after':hypotheses}]
        return {'history':history,'hypotheses':hypotheses,'stop':'SUPPORTED_DIAGNOSIS' if supported else ''}
    def finish(state):
        hypotheses,supported,reason,refs=assess(state)
        report=Report(verdict='MISSING_INGESTION' if supported else 'ESCALATE_AMBIGUOUS',
            reason=reason if supported else state['stop']+': '+reason,evidence=refs,
            next_manual_check='Reconcile source payment keys and values against the import batch; replay missing rows and confirm coverage. Payment-value loss is not established from surviving records alone.',
            points_spent=state['alert']['budget']-state['remaining'],points_remaining=state['remaining'],
            planner=getattr(planner,'name','deterministic-olist-v1'), model_tokens=getattr(planner,'tokens',0))
        return {'report':{**report.model_dump(), 'model_calls':getattr(planner,'calls',[]), 'provider_errors':getattr(planner,'errors',[])},'hypotheses':hypotheses}
    graph=StateGraph(State)
    for name,node in [('initialize',initialize),('plan',plan),('call',call),('evaluate',evaluate),('finish',finish)]:
        graph.add_node(name,node)
    graph.add_edge(START,'initialize'); graph.add_edge('initialize','plan')
    graph.add_conditional_edges('plan',lambda s:'finish' if s['stop'] else 'call')
    graph.add_edge('call','evaluate')
    graph.add_conditional_edges('evaluate',lambda s:'finish' if s['stop'] else 'plan')
    graph.add_edge('finish',END)
    return graph.compile()

async def investigate(alert: Alert, transport, planner=None, on_update=None):
    initial=dict(alert=alert.model_dump(mode='json'),remaining=alert.budget,
        hypotheses=[],history=[],request=None,stop='',report={})
    last=initial
    async for state in build_graph(transport,planner).astream(initial,config={'recursion_limit':100},stream_mode='values'):
        last=state
        if on_update is not None:
            on_update(state)
    return last
