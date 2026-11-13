# Olist data and first incident

Data provided by **Olist**, from the [Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), licensed **CC BY-NC-SA 4.0** as listed by the publisher. Raw files and generated manifests are kept in ignored `data/`. This phase uses orders and payments; the other seven source tables are outside this incident's scope.

## Acquisition and loading

Download the archive from the linked dataset page or use:

```sh
mkdir -p data/olist
curl -L --fail https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce -o data/olist.zip
unzip -o data/olist.zip 'olist_orders_dataset.csv' 'olist_order_payments_dataset.csv' -d data/olist
docker compose --profile data build loader
docker compose --profile data run --rm loader > data/incident-manifest.json
```

If Kaggle requires login, download through its website and place the two CSVs in `data/olist`. Build separately so build output does not enter the JSON report.

The loader defaults to `--replace --incident`. It replaces only the managed Olist tables, telemetry, and ground-truth manifest, in a single transaction. Repeated runs restore the baseline before injection. Failed loads roll back. To restore a healthy baseline:

```sh
docker compose --profile data run --rm loader python -m datamedic.load_olist --replace
```

Only the loader receives administrator credentials. The app has no access to the loader's host data mount. The baseline and ground-truth schemas have no reader grants. The reader sees payment columns and only order ID, status, and purchase timestamp from orders; customer IDs remain restricted. Operations grants/tools arrive in phase 4.

## Source fingerprints and relationships

SHA-256 fingerprints recorded for the downloaded files:

- `olist_orders_dataset.csv`: `8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf`
- `olist_order_payments_dataset.csv`: `4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0`

Orders contain 99,441 rows, uniquely keyed by `order_id`. Payments contain 103,886 rows, keyed by `(order_id, payment_sequential)`, with a validated baseline foreign key to orders. All source columns are loaded with explicit types. Money uses fixed decimal precision. Timestamp fields have no timezone. The working orders table indexes purchase timestamps; payment keys index joins by order ID.

## Measured incident

For purchases on 2018-08-15, deterministic injection removes 102 payment rows worth 18,351.42. The working table has 103,784 payments. Order count remains 288; payment coverage becomes 65.28%. Recorded payment value becomes 34,971.28, or 20.31% below the trailing seven-day mean. Daily aggregates first group payments by order to avoid inflating order counts for multiple payment sequences, and the seven-day denominator includes empty days.

`ops_telemetry.events` contains four explicitly synthetic events: failed payment ingestion with matching expected/actual counts, successful order ingestion, healthy gateway, and unchanged configuration. Each includes the covered purchase window and source ID. These are controlled scenario evidence, not historical Olist operational logs.

The full manifest is saved in `ground_truth.manifest`, including hashes, daily before/after metrics, removed keys, value, and expected diagnosis. Inspect it as administrator:

```sh
docker compose exec postgres-db psql -U datamedic_admin -d olist_db -c 'SELECT payload FROM ground_truth.manifest;'
```

Validation performed: real-data load, repeated load with identical manifest, baseline/working row reconciliation, telemetry inspection, and database schema privilege checks. This is one synthetic development case, not a diagnosis benchmark result.
