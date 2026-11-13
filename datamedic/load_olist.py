"""Transactional Olist baseline loader and deterministic incident generator."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import psycopg
from psycopg import sql

FILES = {
    'orders': ('olist_orders_dataset.csv', 'order_id,customer_id,order_status,order_purchase_timestamp,order_approved_at,order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date'),
    'order_payments': ('olist_order_payments_dataset.csv', 'order_id,payment_sequential,payment_type,payment_installments,payment_value'),
}
DDL = '''
CREATE SCHEMA IF NOT EXISTS baseline;
CREATE SCHEMA IF NOT EXISTS ground_truth;
CREATE SCHEMA IF NOT EXISTS olist;
CREATE SCHEMA IF NOT EXISTS ops_telemetry;
CREATE TABLE IF NOT EXISTS baseline.orders (
 order_id text PRIMARY KEY, customer_id text NOT NULL, order_status text NOT NULL,
 order_purchase_timestamp timestamp NOT NULL, order_approved_at timestamp,
 order_delivered_carrier_date timestamp, order_delivered_customer_date timestamp,
 order_estimated_delivery_date timestamp);
CREATE TABLE IF NOT EXISTS baseline.order_payments (
 order_id text REFERENCES baseline.orders(order_id), payment_sequential integer,
 payment_type text NOT NULL, payment_installments integer NOT NULL,
 payment_value numeric(14,2) NOT NULL,
 PRIMARY KEY (order_id,payment_sequential));
CREATE TABLE IF NOT EXISTS olist.orders (LIKE baseline.orders INCLUDING ALL);
CREATE TABLE IF NOT EXISTS olist.order_payments (LIKE baseline.order_payments INCLUDING ALL);
CREATE INDEX IF NOT EXISTS orders_purchase_date ON olist.orders(order_purchase_timestamp);
CREATE TABLE IF NOT EXISTS ground_truth.manifest (case_id text PRIMARY KEY, payload jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS ops_telemetry.events (
 source_id text PRIMARY KEY, occurred_at timestamp NOT NULL, kind text NOT NULL,
 synthetic boolean NOT NULL DEFAULT true CHECK (synthetic), details jsonb NOT NULL);
'''

METRICS = '''
SELECT d.day::date AS day, count(o.order_id) AS orders,
 count(p.order_id) AS paid_orders, coalesce(sum(p.value),0) AS payment_value
FROM generate_series(timestamp '2018-08-08', timestamp '2018-08-15', interval '1 day') d(day)
LEFT JOIN olist.orders o ON o.order_purchase_timestamp >= d.day
 AND o.order_purchase_timestamp < d.day + interval '1 day'
LEFT JOIN (SELECT order_id, sum(payment_value) value FROM olist.order_payments GROUP BY order_id) p
 ON p.order_id=o.order_id
GROUP BY d.day ORDER BY d.day
'''


def load(directory: Path, incident: bool) -> dict:
    sources = {}
    # Validate headers and fingerprint inputs before touching the database.
    for table, (filename, columns) in FILES.items():
        path = directory / filename
        with path.open(newline='', encoding='utf-8-sig') as stream:
            if next(csv.reader(stream)) != columns.split(','):
                raise ValueError(f'Unexpected CSV header: {filename}')
        with path.open('rb') as stream:
            sources[filename] = hashlib.file_digest(stream, 'sha256').hexdigest()
    with psycopg.connect(connect_timeout=10) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(742198)")
        conn.execute(DDL)
        conn.execute('TRUNCATE baseline.order_payments, baseline.orders, olist.order_payments, olist.orders, ground_truth.manifest, ops_telemetry.events')
        counts = {}
        for table, (filename, columns) in FILES.items():
            query = sql.SQL('COPY baseline.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER true)').format(
                sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns.split(','))))
            with conn.cursor().copy(query) as copy:
                with (directory / filename).open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        copy.write(chunk)
            conn.execute(sql.SQL('INSERT INTO olist.{} SELECT * FROM baseline.{}').format(sql.Identifier(table), sql.Identifier(table)))
            counts[table] = conn.execute(sql.SQL('SELECT count(*) FROM baseline.{}').format(sql.Identifier(table))).fetchone()[0]
        before = conn.execute(METRICS).fetchall()
        removed = []
        if incident:
            eligible = conn.execute('''SELECT o.order_id FROM olist.orders o
                WHERE order_purchase_timestamp >= '2018-08-15' AND order_purchase_timestamp < '2018-08-16'
                AND EXISTS (SELECT 1 FROM olist.order_payments p WHERE p.order_id=o.order_id)
                ORDER BY o.order_id COLLATE "C"''').fetchall()
            keys = [row[0] for row in eligible[:len(eligible) * 35 // 100]]
            if not keys:
                raise ValueError('Insufficient eligible orders for incident; transaction rolled back')
            removed = conn.execute('''DELETE FROM olist.order_payments WHERE order_id=ANY(%s)
                RETURNING order_id,payment_sequential,payment_value''', (keys,)).fetchall()
            removed.sort()
        after = conn.execute(METRICS).fetchall()
        average = sum(row[3] for row in after[:7]) / 7
        target = after[-1]
        if not target[1] or average <= 0:
            raise ValueError('Insufficient target or reference data; transaction rolled back')
        expected = conn.execute('''SELECT count(*) FROM baseline.order_payments p JOIN baseline.orders o USING(order_id)
          WHERE o.order_purchase_timestamp >= '2018-08-15' AND o.order_purchase_timestamp < '2018-08-16' ''').fetchone()[0]
        events = [
            ('etl-payments', 'etl', {'job': 'payments_import', 'status': 'FAILED' if incident else 'SUCCESS', 'expected_rows': expected, 'actual_rows': expected-len(removed), 'exit_code': 1 if incident else 0}),
            ('etl-orders', 'etl', {'job': 'orders_import', 'status': 'SUCCESS', 'expected_rows': target[1], 'actual_rows': target[1], 'exit_code': 0}),
            ('service-payments', 'service', {'service': 'payments_gateway', 'status': 'HEALTHY', 'error_count': 0}),
            ('config-import', 'config', {'component': 'payment_mapping', 'status': 'UNCHANGED', 'version': 'baseline-v1'}),
        ]
        for source_id, kind, details in events:
            details.update(window_start='2018-08-15T00:00:00', window_end='2018-08-16T00:00:00', clock='dataset-local-naive')
            conn.execute('INSERT INTO ops_telemetry.events VALUES (%s,%s,%s,true,%s)',
                         (source_id, '2018-08-16 00:05:00', kind, psycopg.types.json.Jsonb(details)))
        report = dict(version=1, case_id='olist-missing-payments-v1' if incident else 'olist-baseline-v1',
            ground_truth='MISSING_INGESTION' if incident else None, sources_sha256=sources,
            baseline_counts=counts, baseline_metrics=before, incident_metrics=after,
            removed_payment_keys=[row[:2] for row in removed], removed_rows=len(removed),
            removed_value=sum(row[2] for row in removed),
            alert=f'Recorded payment value for orders purchased on 2018-08-15 is {target[3]}, {(average-target[3])/average*100:.2f}% below the trailing seven-day average; order count is {target[1]} and payment coverage is {target[2]/target[1]*100:.2f}%.')
        serialized = json.loads(json.dumps(report, default=str))
        conn.execute('INSERT INTO ground_truth.manifest VALUES (%s,%s)', (report['case_id'], psycopg.types.json.Jsonb(serialized)))
        # Only non-customer diagnostic fields are exposed; no baseline or oracle grants.
        conn.execute('GRANT SELECT (order_id,order_status,order_purchase_timestamp) ON olist.orders TO datamedic_reader')
        conn.execute('GRANT SELECT ON olist.order_payments TO datamedic_reader')
        return serialized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/data'))
    parser.add_argument('--incident', action='store_true')
    parser.add_argument('--replace', action='store_true', help='Explicitly replace DataMedic baseline, working tables, telemetry and manifest')
    args = parser.parse_args()
    if not args.replace:
        parser.error('--replace is required: loading replaces the managed dataset')
    print(json.dumps(load(args.data_dir, args.incident), indent=2))

if __name__ == '__main__':
    main()
