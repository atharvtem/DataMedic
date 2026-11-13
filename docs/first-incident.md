# First release: missing payment ingestion

Case ID: `olist-missing-payments-v1`. Ground truth: `MISSING_INGESTION`.
The first release investigates this one controlled Olist incident. Other
categories are competing explanations, with benchmark cases added in phase 6.

## Metric and time window

Use orders purchased in the half-open window `[2018-08-15, 2018-08-16)`.
Compare with the seven complete preceding purchase dates. Treat source timestamps
as timezone-naive local dataset times; synthetic telemetry uses the same clock.
The metric is recorded payment value by order purchase date, not net revenue or
payment settlement volume. Join `olist.orders.order_id` to
`olist.order_payments.order_id`; payments have no timestamp.

## Reproducible intervention (to implement in phase 2)

Load the official orders and payments CSVs, preserve their SHA-256 hashes and
baseline counts, and retain the baseline outside the agent's permitted schemas.
Select target-day orders with payments, sort by order_id, and remove payments
for the first floor(eligible_order_count * 0.35) orders. Remove all payment
sequences for each selected order. Fail scenario creation if no orders qualify.
Keep orders and remaining payment values unchanged. Record removed keys, counts,
and total value in a ground-truth manifest inaccessible to the investigator.

Seed explicitly synthetic ETL telemetry: the payment import batch failed, with
expected and actual row counts whose difference matches the removed rows and
whose purchase window matches the incident. Seed successful order ingestion and
normal service/configuration records for that window.

Generate the alert from measured post-injection sums and baseline coverage:
“Recorded payment value for orders purchased on 2018-08-15 is X, Y% below
the trailing seven-day average; order count is N and payment coverage is C%.”
Do not hardcode a 35% revenue drop: removing 35% of orders does not imply it.

## Evidence and abstention

Support requires reduced payment coverage, unchanged order headers, an ETL
shortfall matching the affected window/count, and payment aggregates accounting
for the deficit. Normal payment coverage falsifies this particular missing-row
mechanism. Duplicate payment keys support `DUPLICATE_RECORDS`; changed values
with normal coverage suggest `SILENT_LOGIC_CORRUPTION`; correlated service
failures require additional causal evidence for `UPSTREAM_SERVICE_OUTAGE`.

Return `ESCALATE_AMBIGUOUS` if telemetry is absent, contradictory, mismatched,
or multiple mechanisms remain plausible, or if the budget expires before the
required checks. A missing payment row alone does not prove ingestion failure.
Request a source-to-import batch reconciliation in the manual handoff.

## Initial planning settings

Budget: 12 points. Schema discovery and bounded table/coverage health: 1 point
each; distributions: 2; each operations tool: 2; targeted analytical SQL: 5.
Charge attempted calls, including denials and failures; retries incur the same
cost. Connectivity probes are infrastructure checks outside investigations.
Measure latency, returned rows/bytes, and model tokens separately.
