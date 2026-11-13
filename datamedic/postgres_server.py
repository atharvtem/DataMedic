"""Bounded PostgreSQL diagnostics exposed through MCP."""
from datetime import datetime, timedelta
import psycopg
from fastmcp import FastMCP
from datamedic.database import execute
from datamedic.sql_policy import COLUMNS, PolicyError, validate

mcp = FastMCP('DataMedic PostgreSQL')

@mcp.tool
def database_status() -> dict:
    """Infrastructure connectivity check; outside the investigation budget."""
    with psycopg.connect(connect_timeout=3) as conn:
        database, role, readonly = conn.execute("SELECT current_database(),current_user,current_setting('transaction_read_only')").fetchone()
    return dict(database=database, role=role, read_only=readonly == 'on')

@mcp.tool
def inspect_database_schema() -> dict:
    """Cost: 1 point. Discover permitted diagnostic columns and types."""
    result = execute("""SELECT table_name,column_name,data_type FROM information_schema.columns
        WHERE table_schema='olist' AND has_column_privilege(
        'olist.' || table_name, column_name, 'SELECT') ORDER BY table_name,ordinal_position""")
    if result['ok']:
        result['rows'] = [r for r in result['rows'] if r[0] in COLUMNS and r[1] in COLUMNS[r[0]]]
        result['row_count'] = len(result['rows'])
    return result

@mcp.tool
def check_payment_coverage(start: str, end: str) -> dict:
    """Cost: 1 point. Daily order counts, payment coverage, values and zero-value rows.

    Use ISO purchase dates/times without timezone. Window is half-open, at most 31 days.
    Payment sequences are grouped per order before joining to avoid duplicate orders.
    """
    try:
        lower, upper = datetime.fromisoformat(start), datetime.fromisoformat(end)
        if lower.tzinfo or upper.tzinfo or not timedelta(0) < upper-lower <= timedelta(days=31):
            raise ValueError()
    except ValueError:
        return dict(ok=False, code='INVALID_WINDOW', hint='Provide naive ISO start/end timestamps spanning 1 second to 31 days.')
    return execute("""WITH selected AS (
       SELECT order_id,order_purchase_timestamp FROM olist.orders
       WHERE order_purchase_timestamp >= %s AND order_purchase_timestamp < %s
    ), payments AS (
       SELECT p.order_id,count(*) payment_rows,sum(p.payment_value) payment_value,
       count(*) FILTER (WHERE p.payment_value=0) zero_rows
       FROM olist.order_payments p JOIN selected o USING(order_id) GROUP BY p.order_id
    ) SELECT o.order_purchase_timestamp::date purchase_date,count(*) orders,
       count(p.order_id) paid_orders,count(*)-count(p.order_id) missing_payment_orders,
       coalesce(sum(p.payment_rows),0) payment_rows,
       coalesce(sum(p.payment_value),0) payment_value,coalesce(sum(p.zero_rows),0) zero_payment_rows
       FROM selected o LEFT JOIN payments p USING(order_id)
       GROUP BY 1 ORDER BY 1""", (lower, upper))

@mcp.tool
def execute_targeted_analytical_query(sql_query: str) -> dict:
    """Cost: 5 points. Run one governed SELECT, with explicit columns and LIMIT 1–200.

    Supports joins, predicates and COUNT/SUM/AVG/MIN/MAX/COALESCE. CTEs,
    subqueries, arbitrary functions, wildcards, and other schemas are not supported.
    """
    try:
        query = validate(sql_query)
    except (PolicyError, RecursionError):
        return dict(ok=False, code='POLICY_DENIED', hint='Use one SELECT over permitted olist columns, approved aggregates and a literal LIMIT 1–200.')
    result = execute(query)
    result['sql'] = query
    return result

if __name__ == '__main__':
    mcp.run(transport='http', host='0.0.0.0', port=8001)

