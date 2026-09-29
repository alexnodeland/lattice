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
-- On PostgreSQL 16 and later, a role that isn't a superuser (Supabase's
-- `postgres`) must be a member of a role to create a database it owns.
SELECT 'GRANT langfuse TO CURRENT_USER'
WHERE NOT pg_has_role(current_user, 'langfuse', 'MEMBER') \gexec
SELECT 'CREATE DATABASE langfuse OWNER langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse') \gexec
ALTER DATABASE langfuse SET timezone TO 'UTC';
