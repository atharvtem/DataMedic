# Database MCP boundary

The internal FastMCP HTTP endpoint exposes:

| Tool | Planning cost | Behavior |
| --- | --- | --- |
| `inspect_database_schema()` | 1 | Discover granted, permitted columns and types |
| `check_payment_coverage(start, end)` | 1 | Daily counts and payment totals over a half-open purchase window, at most 31 days |
| `execute_targeted_analytical_query(sql_query)` | 5 | Governed analytical SELECT |
| `database_status()` | Infrastructure | Connectivity and reader-role status |

Costs are descriptive until the phase 5 graph enforces accounting. Coverage aggregates payment sequences before joining orders. Days without orders are absent from this tool's output; callers must not treat the number of returned rows as a fixed-day average denominator. The tool uses fixed SQL with bound timestamp values; it accepts no dynamic identifiers.

## Supported SQL

The [SQLGlot parser](https://sqlglot.com/sqlglot.html) reads PostgreSQL syntax. The policy accepts a conservative AST allowlist: a single SELECT, one to three qualified Olist table references, explicitly permitted columns, joins, basic predicates/arithmetic, CASE, and COUNT/SUM/AVG/MIN/MAX/COALESCE. A literal LIMIT from 1 to 200 is required, including for aggregates. COUNT(*) is allowed; projection wildcards are denied. Output aliases cannot be referenced in ORDER BY; repeat the expression instead.

CTEs (including data-modifying CTEs), subqueries, arbitrary functions, casts, unions, locks, writes, multiple statements, unknown syntax, restricted columns, and other schemas are rejected. Queries are limited to 16,000 bytes. Only regenerated, validated SQL is executed. Denials return a structured code and safe guidance without raw database errors.

Example:

```sql
SELECT o.order_status, COUNT(*)
FROM olist.orders o
WHERE o.order_purchase_timestamp >= '2018-08-15'
  AND o.order_purchase_timestamp < '2018-08-16'
GROUP BY o.order_status
LIMIT 20
```

## Execution and permissions

Every diagnostic connection uses read-only transactions, a five-second PostgreSQL statement timeout, a one-second lock timeout, a three-second connection timeout, and a pg_catalog search path. A server cursor fetches at most 201 rows; responses exceeding 200 rows or 65,536 bytes of serialized column/row data return RESULT_LIMIT without partial data. Timeouts return TIMEOUT. SQL LIMIT does not bound query compute; PostgreSQL's [statement timeout](https://www.postgresql.org/docs/16/runtime-config-client.html) independently bounds each statement/fetch. The byte cap applies to returned data, not the complete MCP envelope or database memory.

Database grants independently restrict the reader to the allowed order columns and payment table. Baseline, customer IDs, ground truth, and telemetry are not available to this role. Operations tools arrive separately in phase 4. The loader is an administrator workflow and is not an agent tool.

## Verification

Run with the first Olist incident loaded:

```sh
docker compose exec -T mcp-postgres python - < tests/check_database_boundary.py
```

Passed in Docker: 12 policy rejection cases; row and byte overflow; actual five-second timeout; direct database rejection of writes, customer IDs, and ground truth with default read-only disabled; MCP discovery, permitted schema, coverage, allowed analytical query, and structured denial. The incident coverage check returns 288 orders, 188 with payments, and 100 without payments.

The test uses pg_sleep directly through the execution layer to exercise timeout behavior; model SQL cannot invoke it. These checks describe covered cases, not a universal security guarantee. This interface currently targets the two Olist tables and rejects unsupported SQL rather than promising arbitrary PostgreSQL compatibility.
