#!/usr/bin/env bash
set -euo pipefail

# psql variables quote the identifier and value independently, including unusual
# database names. ON_ERROR_STOP prevents a partial initialization from succeeding.
psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=airflow_db="$AIRFLOW_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'airflow_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'airflow_db')
\gexec
SQL
