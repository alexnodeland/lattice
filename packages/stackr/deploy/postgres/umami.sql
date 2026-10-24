-- Umami's role and database (ADR-0050), on the plain PostgreSQL adapter: umami-db-init runs this
-- with the umami profile alone, on every start; it is idempotent, and the password follows .env,
-- read from the environment, never a command line. A database of its own, owned by its role, no
-- one else may connect to, with its tables in the schema `umami`, the only schema there.
\set ON_ERROR_STOP on

DO $$
BEGIN
  SET log_min_error_statement = panic;
  SET log_min_duration_statement = -1;
EXCEPTION WHEN insufficient_privilege THEN
  NULL;
END $$;

\getenv umami_password UMAMI_DB_PASSWORD
SELECT 'CREATE ROLE umami LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'umami') \gexec
ALTER ROLE umami WITH LOGIN PASSWORD :'umami_password';
SELECT 'CREATE DATABASE umami OWNER umami'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'umami') \gexec
ALTER DATABASE umami SET timezone TO 'UTC';
REVOKE CONNECT ON DATABASE umami FROM PUBLIC;
\connect umami
SET client_min_messages = warning;
CREATE SCHEMA IF NOT EXISTS umami AUTHORIZATION umami;
-- Its database's own `public` schema, which the database's owner would hold, isn't kept.
DROP SCHEMA IF EXISTS public;
ALTER ROLE umami IN DATABASE umami SET search_path TO umami;
