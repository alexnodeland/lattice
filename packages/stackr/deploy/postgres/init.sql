-- A role and a database for each of the stack's services that keep data in
-- PostgreSQL, on whichever PostgreSQL is the database adapter (ADR-0005).
-- db-init runs this on every start: it is idempotent, and passwords follow
-- .env. psql reads them from the environment, so they never appear in a
-- command line.
\set ON_ERROR_STOP on

-- GoTrue's migrations grant to a postgres role: plain PostgreSQL, local Supabase and RDS (whose
-- master is named so) have one; Floci's RDS needn't (stackr ADR-0025).
SELECT 'CREATE ROLE postgres NOLOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') \gexec

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

-- The AWS recipe's own (stackr ADR-0034), each only when its password is given: on one machine,
-- neither is.
\connect postgres

-- Grafana's users and alert state, on PostgreSQL rather than its task's disk.
\getenv grafana_password GRAFANA_DB_PASSWORD
\if :{?grafana_password}
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
\endif

-- The application's database, and its owner, which migrates it. With grantr, its db-roles
-- creates the role the application works as, so the owner may create roles: on PostgreSQL 16
-- and later, it administers only the roles it creates.
\getenv app_db_name APP_DB_NAME
\getenv app_db_password APP_DB_PASSWORD
\if :{?app_db_password}
SELECT format('CREATE ROLE %I LOGIN', :'app_db_name')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_db_name') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN CREATEROLE PASSWORD %L', :'app_db_name', :'app_db_password') \gexec
SELECT CASE
  WHEN current_setting('server_version_num')::int >= 160000
    THEN NOT pg_has_role(current_user, :'app_db_name', 'SET')
  ELSE NOT pg_has_role(current_user, :'app_db_name', 'MEMBER')
END AS needs_grant \gset
\if :needs_grant
SELECT format('GRANT %I TO CURRENT_USER', :'app_db_name') \gexec
\endif
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db_name', :'app_db_name')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'app_db_name') \gexec
SELECT format('ALTER DATABASE %I SET timezone TO %L', :'app_db_name', 'UTC') \gexec
\endif
