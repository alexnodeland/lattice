-- A role and a database for each of the stack's services that keep data in
-- PostgreSQL, on whichever PostgreSQL is the database adapter (ADR-0005).
-- db-init runs this on every start: it is idempotent, and passwords follow
-- .env. psql reads them from the environment, so they never appear in a
-- command line.
\set ON_ERROR_STOP on

-- Keep the statements that carry passwords out of the server's log, where the server lets this
-- role say so: a superuser, or RDS's rds_superuser, may; another role keeps the server's settings.
DO $$
BEGIN
  SET log_min_error_statement = panic;
  SET log_min_duration_statement = -1;
EXCEPTION WHEN insufficient_privilege THEN
  NULL;
END $$;

-- Langfuse
\getenv langfuse_password LANGFUSE_DB_PASSWORD
SELECT 'CREATE ROLE langfuse LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'langfuse') \gexec
ALTER ROLE langfuse WITH LOGIN PASSWORD :'langfuse_password';
-- To create a database owned by the role, the admin role must be able to SET
-- ROLE to it. A superuser always can. Supabase's `postgres` isn't one: on
-- PostgreSQL 16 and later, creating a role makes it an admin of the role but
-- without SET, so it needs a grant of its own.
SELECT CASE
  WHEN current_setting('server_version_num')::int >= 160000
    THEN NOT pg_has_role(current_user, 'langfuse', 'SET')
  ELSE NOT pg_has_role(current_user, 'langfuse', 'MEMBER')
END AS needs_grant \gset
\if :needs_grant
GRANT langfuse TO CURRENT_USER;
\endif
SELECT 'CREATE DATABASE langfuse OWNER langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse') \gexec
ALTER DATABASE langfuse SET timezone TO 'UTC';

-- LiteLLM
\getenv litellm_password LITELLM_DB_PASSWORD
SELECT 'CREATE ROLE litellm LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'litellm') \gexec
ALTER ROLE litellm WITH LOGIN PASSWORD :'litellm_password';
SELECT CASE
  WHEN current_setting('server_version_num')::int >= 160000
    THEN NOT pg_has_role(current_user, 'litellm', 'SET')
  ELSE NOT pg_has_role(current_user, 'litellm', 'MEMBER')
END AS needs_grant \gset
\if :needs_grant
GRANT litellm TO CURRENT_USER;
\endif
SELECT 'CREATE DATABASE litellm OWNER litellm'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm') \gexec

-- The AWS recipe's own (stackr ADR-0034), each only when it is given: on one machine, neither is,
-- and this runs as it always has.
\getenv grafana_password GRAFANA_DB_PASSWORD
\getenv app_db_name APP_DB_NAME
\getenv app_db_password APP_DB_PASSWORD
\getenv app_db_creates_roles APP_DB_CREATES_ROLES
\getenv app_db_schema APP_DB_SCHEMA

\if :{?grafana_password}
-- Grafana's users and alert state, on PostgreSQL rather than its task's disk.
SELECT 'CREATE ROLE grafana LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana') \gexec
ALTER ROLE grafana WITH LOGIN PASSWORD :'grafana_password';
SELECT CASE
  WHEN current_setting('server_version_num')::int >= 160000
    THEN NOT pg_has_role(current_user, 'grafana', 'SET')
  ELSE NOT pg_has_role(current_user, 'grafana', 'MEMBER')
END AS needs_grant \gset
\if :needs_grant
GRANT grafana TO CURRENT_USER;
\endif
SELECT 'CREATE DATABASE grafana OWNER grafana'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'grafana') \gexec
-- Only Grafana, its owner, connects to it.
REVOKE CONNECT ON DATABASE grafana FROM PUBLIC;
\endif

\if :{?app_db_password}
\if :{?app_db_name}
-- The application's database, and its owner, which migrates it. With grantr, its db-roles
-- creates the role the application works as, so the owner may create roles
-- (APP_DB_CREATES_ROLES): on PostgreSQL 16 and later, a role that may create roles administers
-- only those it creates, so this needs 16.
SELECT current_setting('server_version_num')::int < 160000 AS too_old \gset
\if :too_old
DO $$ BEGIN RAISE EXCEPTION 'the application''s owner needs PostgreSQL 16 or later'; END $$;
\endif
SELECT 'CREATE ROLE ' || quote_ident(:'app_db_name') || ' LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_db_name') \gexec
\if :{?app_db_creates_roles}
ALTER ROLE :"app_db_name" WITH LOGIN CREATEROLE PASSWORD :'app_db_password';
\else
ALTER ROLE :"app_db_name" WITH LOGIN NOCREATEROLE PASSWORD :'app_db_password';
\endif
SELECT NOT pg_has_role(current_user, :'app_db_name', 'SET') AS needs_grant \gset
\if :needs_grant
GRANT :"app_db_name" TO CURRENT_USER;
\endif
SELECT 'CREATE DATABASE ' || quote_ident(:'app_db_name') || ' OWNER ' || quote_ident(:'app_db_name')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db_name') \gexec
ALTER DATABASE :"app_db_name" SET timezone TO 'UTC';
-- The owner's search_path is the application's schema, in its database, as the role's own: the
-- application asks for it as it connects too, but a proxy that drops what a client asks for at
-- its start, as Floci's RDS does, would leave the owner migrating into another schema.
-- Without APP_DB_SCHEMA, the owner keeps the server's default, and loses one set before.
\if :{?app_db_schema}
SELECT :'app_db_schema' = '' AS schema_empty \gset
\if :schema_empty
DO $$ BEGIN RAISE EXCEPTION 'APP_DB_SCHEMA is empty: name the application''s schema, or leave it unset'; END $$;
\endif
ALTER ROLE :"app_db_name" IN DATABASE :"app_db_name" SET search_path TO :"app_db_schema";
\else
ALTER ROLE :"app_db_name" IN DATABASE :"app_db_name" RESET search_path;
\endif
\endif
\endif

-- GoTrue (the auth profile): its own database, whose `auth` schema it owns and
-- migrates. Its migrations grant to a `postgres` role, which plain PostgreSQL
-- and local Supabase have, and which RDS has when its master is named so
-- (stackr ADR-0025).
\getenv auth_password AUTH_DB_PASSWORD
SELECT 'CREATE ROLE gotrue LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gotrue') \gexec
ALTER ROLE gotrue WITH LOGIN PASSWORD :'auth_password';
ALTER ROLE gotrue SET search_path TO auth;
SELECT CASE
  WHEN current_setting('server_version_num')::int >= 160000
    THEN NOT pg_has_role(current_user, 'gotrue', 'SET')
  ELSE NOT pg_has_role(current_user, 'gotrue', 'MEMBER')
END AS needs_grant \gset
\if :needs_grant
GRANT gotrue TO CURRENT_USER;
\endif
SELECT 'CREATE DATABASE auth OWNER gotrue'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auth') \gexec
ALTER DATABASE auth SET timezone TO 'UTC';
-- Only GoTrue, its owner, connects to it.
REVOKE CONNECT ON DATABASE auth FROM PUBLIC;
\connect auth
CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION gotrue;

