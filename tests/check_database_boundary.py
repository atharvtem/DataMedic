"""Run inside mcp-postgres after the Olist incident is loaded."""
import asyncio
import psycopg
from fastmcp import Client
from datamedic.sql_policy import validate, PolicyError
from datamedic.database import execute

bad = [
 'DELETE FROM olist.orders', 'SELECT 1; SELECT 2',
 'WITH x AS (DELETE FROM olist.orders RETURNING *) SELECT * FROM x',
 'SELECT customer_id FROM olist.orders LIMIT 2',
 'SELECT * FROM olist.orders LIMIT 2',
 'SELECT order_id FROM baseline.orders LIMIT 2',
 'SELECT pg_sleep(10) FROM olist.orders LIMIT 1',
 'SELECT order_id FROM olist.orders',
 'SELECT order_id FROM olist.orders LIMIT 201',
 'SELECT order_id FROM olist.orders FOR UPDATE LIMIT 1',
 'SELECT (SELECT 1) FROM olist.orders LIMIT 1',
 'SELECT ( FROM',
]
for query in bad:
    try:
        validate(query)
    except PolicyError:
        continue
    raise AssertionError(query)
assert execute('SELECT order_id FROM olist.orders', max_rows=1)['code'] == 'RESULT_LIMIT'
assert execute('SELECT order_id FROM olist.orders LIMIT 1', max_bytes=10)['code'] == 'RESULT_LIMIT'
assert execute('SELECT pg_sleep(6)')['code'] == 'TIMEOUT'
for query in ['DELETE FROM olist.order_payments WHERE false',
              'SELECT customer_id FROM olist.orders LIMIT 1',
              'SELECT payload FROM ground_truth.manifest LIMIT 1']:
    try:
        # Explicitly turn off the default read-only setting to verify grants independently.
        with psycopg.connect(options='-c default_transaction_read_only=off') as conn:
            conn.execute(query)
    except psycopg.errors.InsufficientPrivilege:
        continue
    raise AssertionError('Database grants failed: '+query)

async def check():
    async with Client('http://localhost:8001/mcp') as client:
        names = {t.name for t in await client.list_tools()}
        assert {'inspect_database_schema','check_payment_coverage','execute_targeted_analytical_query'} <= names
        schema = (await client.call_tool('inspect_database_schema',{})).data
        assert schema['ok'] and all(r[1]!='customer_id' for r in schema['rows'])
        coverage = (await client.call_tool('check_payment_coverage',{'start':'2018-08-15','end':'2018-08-16'})).data
        assert coverage['ok'], coverage
        assert coverage['rows'][0][1:4] == [288,188,100], coverage
        allowed = (await client.call_tool('execute_targeted_analytical_query',{'sql_query':"SELECT o.order_status, COUNT(*) FROM olist.orders o LEFT JOIN olist.order_payments p ON p.order_id=o.order_id GROUP BY o.order_status LIMIT 20"})).data
        assert allowed['ok'], allowed
        denied = (await client.call_tool('execute_targeted_analytical_query',{'sql_query':'DROP TABLE olist.orders'})).data
        assert denied['code']=='POLICY_DENIED'
        print('Passed: 12 policy denials, row/byte limits, timeout, 3 independent DB permission checks, MCP discovery, schema, coverage, SELECT, denial')
asyncio.run(check())
