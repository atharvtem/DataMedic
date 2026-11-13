"""Read-only, bounded tools for explicitly synthetic operational evidence."""
from datetime import datetime, timedelta
import psycopg
from fastmcp import FastMCP
from datamedic.database import execute

mcp = FastMCP('DataMedic Operations')

@mcp.tool
def database_status() -> dict:
    """Infrastructure connectivity check outside the incident budget."""
    with psycopg.connect(connect_timeout=3) as conn:
        database, role, readonly = conn.execute("SELECT current_database(),current_user,current_setting('transaction_read_only')").fetchone()
    return dict(database=database, role=role, read_only=readonly == 'on')


def events(kind: str, end: str, window_hours: int, status_filter: str | None = None) -> dict:
    try:
        upper = datetime.fromisoformat(end)
        if upper.tzinfo or isinstance(window_hours, bool) or not 1 <= window_hours <= 168:
            raise ValueError()
        lower = upper - timedelta(hours=window_hours)
        if status_filter is not None and status_filter not in {'SUCCESS', 'FAILED', 'RUNNING'}:
            raise ValueError()
    except (ValueError, OverflowError):
        return dict(ok=False, code='INVALID_WINDOW_OR_FILTER', hint='Use a naive ISO end timestamp, 1–168 hours, and SUCCESS/FAILED/RUNNING for ETL status.')
    result = execute('''SELECT source_id,occurred_at,kind,synthetic,details
        FROM ops_telemetry.events WHERE kind=%s AND occurred_at >= %s AND occurred_at < %s
        AND (%s::text IS NULL OR details->>'status'=%s)
        ORDER BY occurred_at,source_id LIMIT 101''', (kind, lower, upper, status_filter, status_filter), max_rows=100)
    if result['ok']:
        result['records'] = [dict(zip(result['columns'], row)) for row in result.pop('rows')]
        result['window'] = dict(start=lower.isoformat(), end=upper.isoformat(), clock='dataset-local-naive')
    return result

@mcp.tool
def query_etl_pipeline_logs(end: str, window_hours: int = 48, status_filter: str | None = None) -> dict:
    """Cost: 2 points. Synthetic ingestion evidence by event time in [end-hours, end).

    End is required so historical investigations never silently use today's clock.
    Returns at most 100 records or an explicit limit error; narrow the window on overflow.
    """
    return events('etl', end, window_hours, status_filter)

@mcp.tool
def check_upstream_service_events(end: str, window_hours: int = 48) -> dict:
    """Cost: 2 points. Synthetic service health events with source IDs and timestamps."""
    return events('service', end, window_hours)

@mcp.tool
def inspect_config_deployments(end: str, window_hours: int = 48) -> dict:
    """Cost: 2 points. Synthetic configuration records with source IDs and timestamps."""
    return events('config', end, window_hours)

if __name__ == '__main__':
    mcp.run(transport='http', host='0.0.0.0', port=8002)
