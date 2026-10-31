-- Spike #942: can a security-definer function check the tenant first and keep every
-- application role off vault.decrypted_secrets? Run as supabase_admin (the self-hosted owner).
\set ON_ERROR_STOP off
\echo '== setup, as supabase_admin'
create role lattice_app login password 'spike-only' noinherit;
create schema lattice;
grant usage on schema lattice to lattice_app;

-- The metadata table RFC-0011 names, with lattice_core.sql's tenant policy.
create table lattice.lattice_secrets (
  id text primary key,                 -- the SecretRef's id, sec_ + 16 hex
  tenant_id text not null,
  purpose text not null,
  vault_id uuid not null
);
alter table lattice.lattice_secrets enable row level security;
create policy lattice_secrets_tenant on lattice.lattice_secrets
  using (tenant_id = current_setting('lattice.tenant_id', true))
  with check (tenant_id = current_setting('lattice.tenant_id', true));
grant select on lattice.lattice_secrets to lattice_app;
alter table lattice.lattice_secrets owner to postgres;

-- put: the tenant comes from the transaction's setting, never from an argument.
create function lattice.put_secret(ref text, purpose text, value text) returns void
language plpgsql security definer set search_path = '' as $$
declare
  tenant text := nullif(current_setting('lattice.tenant_id', true), '');
  vid uuid;
begin
  if tenant is null then raise exception 'no tenant' using errcode = '42501'; end if;
  vid := vault.create_secret(value, ref, purpose);
  insert into lattice.lattice_secrets values (ref, tenant, purpose, vid);
end $$;

-- read: check the tenant first, then read the view. The owner (postgres) bypasses RLS, so the
-- tenant check is explicit in the WHERE, not left to the policy.
create function lattice.read_secret(ref text) returns text
language plpgsql security definer set search_path = '' as $$
declare
  tenant text := nullif(current_setting('lattice.tenant_id', true), '');
  vid uuid;
  val text;
begin
  if tenant is null then raise exception 'no tenant' using errcode = '42501'; end if;
  select s.vault_id into vid from lattice.lattice_secrets s where s.id = ref and s.tenant_id = tenant;
  if vid is null then raise exception 'no such secret for this tenant' using errcode = '42501'; end if;
  select d.decrypted_secret into val from vault.decrypted_secrets d where d.id = vid;
  return val;
end $$;

create function lattice.rotate_secret(ref text, value text) returns void
language plpgsql security definer set search_path = '' as $$
declare
  tenant text := nullif(current_setting('lattice.tenant_id', true), '');
  vid uuid;
begin
  select s.vault_id into vid from lattice.lattice_secrets s where s.id = ref and s.tenant_id = tenant;
  if vid is null then raise exception 'no such secret for this tenant' using errcode = '42501'; end if;
  perform vault.update_secret(vid, value);
end $$;

alter function lattice.put_secret(text, text, text) owner to postgres;
alter function lattice.read_secret(text) owner to postgres;
alter function lattice.rotate_secret(text, text) owner to postgres;
revoke all on function lattice.put_secret(text, text, text), lattice.read_secret(text),
  lattice.rotate_secret(text, text) from public;
grant execute on function lattice.put_secret(text, text, text), lattice.read_secret(text),
  lattice.rotate_secret(text, text) to lattice_app;

\echo '== as lattice_app: two tenants put a secret each'
set role lattice_app;
begin; select set_config('lattice.tenant_id', 'tenant-a', true);
select lattice.put_secret('sec_aaaaaaaaaaaaaaaa', 'forge:token', 'TOKEN-OF-TENANT-A'); commit;
begin; select set_config('lattice.tenant_id', 'tenant-b', true);
select lattice.put_secret('sec_bbbbbbbbbbbbbbbb', 'litellm:key', 'KEY-OF-TENANT-B'); commit;

\echo '== as lattice_app: tenant-a reads its own, then tries tenant-b''s'
begin; select set_config('lattice.tenant_id', 'tenant-a', true);
select lattice.read_secret('sec_aaaaaaaaaaaaaaaa') as tenant_a_reads_own;
select lattice.read_secret('sec_bbbbbbbbbbbbbbbb') as tenant_a_reads_b; rollback;

\echo '== as lattice_app: no tenant set'
select lattice.read_secret('sec_aaaaaaaaaaaaaaaa') as no_tenant;

\echo '== as lattice_app: RLS on the metadata table, tenant-b sees only its row'
begin; select set_config('lattice.tenant_id', 'tenant-b', true);
select id, tenant_id from lattice.lattice_secrets; rollback;

\echo '== as lattice_app: rotate (vault.update_secret) and read the new value'
begin; select set_config('lattice.tenant_id', 'tenant-a', true);
select lattice.rotate_secret('sec_aaaaaaaaaaaaaaaa', 'TOKEN-OF-TENANT-A-v2');
select lattice.read_secret('sec_aaaaaaaaaaaaaaaa') as after_rotate; commit;

\echo '== as lattice_app: the view, the table, the decrypt function and create_secret directly'
select count(*) from vault.decrypted_secrets;
select count(*) from vault.secrets;
select vault._crypto_aead_det_decrypt(''::bytea, ''::bytea, 0);
select vault.create_secret('x');
reset role;

\echo '== Supabase''s own roles, as the image ships them'
select r as role, has_table_privilege(r, 'vault.decrypted_secrets', 'select') as view_select,
  has_function_privilege(r, 'vault._crypto_aead_det_decrypt(bytea,bytea,bigint,bytea,bytea)', 'execute') as decrypt_exec
from unnest(array['lattice_app','anon','authenticated','authenticator','service_role','postgres']) r;

\echo '== as postgres (what a hosted project''s owner is): try to take service_role off the view'
set role postgres;
revoke select on vault.decrypted_secrets from service_role;
revoke usage on schema vault from service_role;
reset role;
select has_table_privilege('service_role', 'vault.decrypted_secrets', 'select') as service_role_still_reads;

\echo '== as supabase_admin (the self-hosted superuser): take service_role off'
revoke all on vault.decrypted_secrets, vault.secrets from service_role;
revoke execute on function vault._crypto_aead_det_decrypt(bytea,bytea,bigint,bytea,bytea),
  vault.create_secret(text,text,text,uuid), vault.update_secret(uuid,text,text,text,uuid) from service_role;
revoke usage on schema vault from service_role;
select r as role, has_table_privilege(r, 'vault.decrypted_secrets', 'select') as view_select,
  has_function_privilege(r, 'vault._crypto_aead_det_decrypt(bytea,bytea,bigint,bytea,bytea)', 'execute') as decrypt_exec
from unnest(array['lattice_app','anon','authenticated','authenticator','service_role','postgres']) r;

\echo '== the function still works for lattice_app after the revokes (its owner is postgres)'
set role lattice_app;
begin; select set_config('lattice.tenant_id', 'tenant-b', true);
select lattice.read_secret('sec_bbbbbbbbbbbbbbbb') as tenant_b_reads_own; rollback;
reset role;

\echo '== ciphertext at rest'
select name, left(secret, 24) || '...' as secret_column, key_id from vault.secrets order by name;
