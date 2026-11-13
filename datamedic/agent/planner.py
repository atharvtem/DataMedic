"""Deterministic development planner; no provider key or ground truth access."""
from datetime import date, datetime, time, timedelta
from datamedic.agent.models import Hypothesis, ToolRequest

COSTS = {'inspect_database_schema':1, 'check_payment_coverage':1,
         'query_etl_pipeline_logs':2, 'check_upstream_service_events':2,
         'inspect_config_deployments':2, 'execute_targeted_analytical_query':5}
SERVERS = {name: ('ops' if name in {'query_etl_pipeline_logs','check_upstream_service_events','inspect_config_deployments'} else 'database') for name in COSTS}

class DeterministicPlanner:
    def hypotheses(self):
        return [Hypothesis(category=c,description=d).model_dump() for c,d in [
            ('MISSING_INGESTION','Payment ingestion omitted rows for the purchase window.'),
            ('SILENT_LOGIC_CORRUPTION','Payment values or mappings changed despite successful ingestion.'),
            ('UPSTREAM_SERVICE_OUTAGE','A gateway incident prevented payment processing.'),
            ('DUPLICATE_RECORDS','Duplicate payment records distorted the reported metric.')]]

    def next(self, state):
        day = date.fromisoformat(state['alert']['purchase_date'])
        end = datetime.combine(day+timedelta(days=1),time(1)).isoformat()
        sequence = [ToolRequest(tool='inspect_database_schema'),
            ToolRequest(tool='check_payment_coverage',arguments={'start':(day-timedelta(days=7)).isoformat(),'end':(day+timedelta(days=1)).isoformat()}),
            ToolRequest(tool='query_etl_pipeline_logs',arguments={'end':end,'window_hours':48}),
            ToolRequest(tool='check_upstream_service_events',arguments={'end':end,'window_hours':48}),
            ToolRequest(tool='inspect_config_deployments',arguments={'end':end,'window_hours':48})]
        done = {h['tool'] for h in state['history']}
        return next((r.model_dump() for r in sequence if r.tool not in done), None)
