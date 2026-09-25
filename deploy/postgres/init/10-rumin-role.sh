#!/bin/sh
# Runs once, when the database volume is first initialised (Phase 10): RUMIN's API connects
# as `rumin`, an ordinary role that owns the `rumin` database and nothing else — not the
# `postgres` superuser, which stays for administration (restores) inside the container.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=app_password="$RUMIN_DB_PASSWORD" <<'SQL'
CREATE ROLE rumin LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'app_password';
CREATE DATABASE rumin OWNER rumin;
REVOKE ALL ON DATABASE rumin FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE rumin TO rumin;
SQL
