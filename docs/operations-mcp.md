# Operations MCP

The private `mcp-ops:8002/mcp` endpoint serves three tools, each with a descriptive cost of two points (budget enforcement arrives in phase 5):

- `query_etl_pipeline_logs(end, window_hours=48, status_filter=None)`
- `check_upstream_service_events(end, window_hours=48)`
- `inspect_config_deployments(end, window_hours=48)`

`end` is a required timezone-naive ISO timestamp in the dataset's clock. Windows are half-open `[end - window_hours, end)` and bounded to 1–168 hours. Queries filter event timestamps; each event separately carries its affected purchase window. For the seeded incident, use `end="2018-08-16T01:00:00"` to include ingestion evidence recorded after the purchase day closes.

Results include source ID, event timestamp, kind, a synthetic flag, and structured details. ETL details include expected and actual counts, status, exit code, and affected window. Optional ETL status accepts SUCCESS, FAILED or RUNNING. Empty results do not establish service health or absence of a configuration change.

All values are parameterized. Queries use the shared executor's read-only transactions, timeout and 64 KiB data cap, with a tighter 100-record cap. Overflow returns RESULT_LIMIT and no partial records. The dedicated `datamedic_ops_reader` has SELECT access only to the ops_telemetry schema. It cannot read Olist or ground truth or mutate telemetry. App health/discovery checks both MCP endpoints and the app holds no database credentials.

`MCP_OPS_PASSWORD` configures the separate reader password; the default is a local-development credential for compatibility with existing `.env` files. Fresh volumes initialize the role automatically. For existing volumes, after adding the configuration:

```sh
docker compose up --build --wait postgres-db
docker compose exec -T postgres-db bash -s < docker/init-db.sh
docker compose up --build -d
```

Initialization is repeatable and does not delete data. Default privileges cover telemetry tables created by the configured administrator loader. If the loader owner changes, its default privileges must also be configured.

Verified in Docker: app-to-both-MCP connectivity; discovery and all three ops tools; structured synthetic records; ETL count deficit of 102 matching the seeded incident; failed-status filtering; exclusive end boundary; invalid timestamps, timezone, oversized windows and status filters. Direct database checks with read-only defaults disabled independently rejected Olist reads, ground-truth reads and telemetry writes.

```sh
docker compose exec -T datamedic-app python - < tests/check_ops_boundary.py
```
