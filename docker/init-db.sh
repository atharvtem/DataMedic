#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=reader_password="$MCP_DB_PASSWORD" --set=ops_password="${MCP_OPS_PASSWORD:-local-ops-reader-only}" --set=ON_ERROR_STOP=1 <<'SQL'
SELECT 'CREATE ROLE datamedic_reader LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'datamedic_reader') \gexec
ALTER ROLE datamedic_reader PASSWORD :'reader_password';
ALTER ROLE datamedic_reader SET default_transaction_read_only = on;
ALTER ROLE datamedic_reader SET statement_timeout = '5s';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS olist;
CREATE SCHEMA IF NOT EXISTS ops_telemetry;
GRANT USAGE ON SCHEMA olist TO datamedic_reader;
SELECT 'CREATE ROLE datamedic_ops_reader LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'datamedic_ops_reader') \gexec
ALTER ROLE datamedic_ops_reader PASSWORD :'ops_password';
ALTER ROLE datamedic_ops_reader SET default_transaction_read_only = on;
ALTER ROLE datamedic_ops_reader SET statement_timeout = '5s';
GRANT USAGE ON SCHEMA ops_telemetry TO datamedic_ops_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops_telemetry GRANT SELECT ON TABLES TO datamedic_ops_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA ops_telemetry TO datamedic_ops_reader;
SQL
