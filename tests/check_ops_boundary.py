"""Run in the app container with the seeded missing-payment incident."""
import asyncio
from fastmcp import Client

async def main():
    async with Client('http://mcp-ops:8002/mcp') as client:
        names = {t.name for t in await client.list_tools()}
        assert {'query_etl_pipeline_logs','check_upstream_service_events','inspect_config_deployments'} <= names
        for tool, count in [('query_etl_pipeline_logs',2),('check_upstream_service_events',1),('inspect_config_deployments',1)]:
            result = (await client.call_tool(tool, {'end':'2018-08-16T01:00:00','window_hours':48})).data
            assert result['ok'] and result['row_count']==count, result
            assert all(r['synthetic'] and isinstance(r['details'],dict) and r['source_id'] for r in result['records'])
        result = (await client.call_tool('query_etl_pipeline_logs', {'end':'2018-08-16T01:00:00','status_filter':'FAILED'})).data
        assert len(result['records'])==1
        details = result['records'][0]['details']
        assert details['expected_rows']-details['actual_rows']==102
        empty = (await client.call_tool('query_etl_pipeline_logs',{'end':'2018-08-16T00:05:00'})).data
        assert empty['ok'] and empty['row_count']==0 # exclusive end boundary
        for args in [{'end':'bad'}, {'end':'2018-08-16','window_hours':169}, {'end':'2018-08-16T01:00:00+00:00'}, {'end':'2018-08-16','status_filter':'anything'}]:
            denied = (await client.call_tool('query_etl_pipeline_logs',args)).data
            assert not denied['ok']
    async with Client('http://mcp-postgres:8001/mcp') as client:
        assert (await client.call_tool('inspect_database_schema',{})).data['ok']
    print('Passed: both MCP servers reachable from app; 3 ops tools, structured synthetic records, matching ETL deficit, status filter, end boundary, invalid input cases')
asyncio.run(main())
