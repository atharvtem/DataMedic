"""Bounded execution shared by fixed diagnostics and governed analytical SQL."""
import json
import time
import psycopg

MAX_ROWS = 200
MAX_BYTES = 65536


def execute(query, params=None, *, max_rows=MAX_ROWS, max_bytes=MAX_BYTES):
    started = time.monotonic()
    try:
        with psycopg.connect(connect_timeout=3, options='-c statement_timeout=5000 -c lock_timeout=1000 -c default_transaction_read_only=on -c search_path=pg_catalog') as conn:
            # Server cursor prevents buffering an unbounded result in the client.
            with conn.cursor(name='diagnostic') as cursor:
                cursor.execute(query, params)
                columns = [col.name for col in cursor.description]
                rows = []
                for row in cursor.fetchmany(max_rows + 1):
                    rows.append([str(v) if not isinstance(v, (str, int, float, bool, dict, list, type(None))) else v for v in row])
                    if len(rows) > max_rows or len(json.dumps({'columns': columns, 'rows': rows}).encode()) > max_bytes:
                        return {'ok': False, 'code': 'RESULT_LIMIT', 'hint': 'Narrow the date window or aggregate the result.'}
        return {'ok': True, 'columns': columns, 'rows': rows, 'row_count': len(rows),
                'result_bytes': len(json.dumps({'columns': columns, 'rows': rows}).encode()),
                'elapsed_ms': round((time.monotonic()-started)*1000, 2)}
    except psycopg.errors.QueryCanceled:
        return {'ok': False, 'code': 'TIMEOUT', 'hint': 'Use a smaller purchase window and fewer joins.'}
    except psycopg.Error:
        return {'ok': False, 'code': 'DATABASE_ERROR', 'hint': 'Check permitted columns, query types, and database availability.'}
