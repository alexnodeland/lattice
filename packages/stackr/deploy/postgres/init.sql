-- A role and a database for each of the stack's services that keep data in
-- PostgreSQL, on whichever PostgreSQL is the database adapter (ADR-0005).
-- db-init runs this on every start: it is idempotent, and passwords follow
-- .env. psql reads them from the environment, so they never appear in a
-- command line.
\set ON_ERROR_STOP on

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
