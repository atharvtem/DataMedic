"""Live MCP run followed by graph control and conflicting-evidence fixtures."""
import asyncio
import copy
from datamedic.agent.graph import investigate
from datamedic.agent.models import Alert
from datamedic.agent.planner import DeterministicPlanner
from datamedic.agent.transport import MCPTransport

class Replay:
    def __init__(self,results):
        self.results=results
    async def call(self,server,name,arguments):
        return copy.deepcopy(self.results[name])

class Repeating(DeterministicPlanner):
    def next(self,state):
        return {'tool':'inspect_database_schema','arguments':{}}

class Unknown(DeterministicPlanner):
    def next(self,state):
        return {'tool':'delete_database'}

async def main():
    alert=Alert(text='Payment coverage anomaly')
    live=await investigate(alert,MCPTransport())
    assert live['report']['verdict']=='MISSING_INGESTION',live['report']
    assert live['remaining']==4 and len(live['history'])==5
    results={h['tool']:h['result'] for h in live['history']}
    for budget in [0,1,3,7]:
        run=await investigate(Alert(text='Anomaly',budget=budget),Replay(results))
        assert run['report']['verdict']=='ESCALATE_AMBIGUOUS'
        assert run['remaining']>=0 and sum(h['cost'] for h in run['history'])<=budget
    missing=copy.deepcopy(results)
    missing['query_etl_pipeline_logs']['records']=[]
    conflict=copy.deepcopy(results)
    conflict['check_upstream_service_events']['records'][0]['details']['status']='OUTAGE'
    mismatch=copy.deepcopy(results)
    mismatch['query_etl_pipeline_logs']['records'][0]['details']['window_start']='2018-08-14T00:00:00'
    for fixture in [missing,conflict,mismatch]:
        run=await investigate(alert,Replay(fixture))
        assert run['report']['verdict']=='ESCALATE_AMBIGUOUS',run['report']
    failures={name:{'ok':False,'code':'TIMEOUT'} for name in results}
    run=await investigate(alert,Replay(failures))
    assert run['report']['points_spent']==8 and run['report']['verdict']=='ESCALATE_AMBIGUOUS'
    repeat=await investigate(alert,Replay(results),Repeating())
    assert repeat['stop']=='RETRY_LIMIT' and len(repeat['history'])==2
    unknown=await investigate(alert,Replay(results),Unknown())
    assert unknown['stop']=='TOOL_UNAVAILABLE' and not unknown['history']
    print('Passed live diagnosis (8/12 points), four low budgets, missing/conflicting/mismatched evidence, charged failures, retry limit, unavailable tool')
asyncio.run(main())
