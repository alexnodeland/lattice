# ADR-0034: Two secrets stores in 0.3.0: Supabase Vault where Postgres can hold it, AWS Secrets Manager on AWS

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Amends:** [lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md), "The secrets port", Decisions O4 and T7, and its non-goal on cloud secrets adapters

## Context

[lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md) puts secrets behind one port, `lattice_core.secrets`, with Supabase Vault as its first adapter (Decision O4), "in the stack it already has". It leaves cloud adapters to 0.3.x (Decision T7). It lists as Unverified Vault's API in the stack's pinned Supabase, whether a security-definer function can check the tenant and keep every application role off the decrypted view, and whether Vault's key stays outside a database dump.

The spike for [#942](https://github.com/alexnodeland/lattice/issues/942) checked them on 2026-10-31, against `supabase/postgres:17.6.1.171`, the image Supabase CLI 2.118.0 (stackr's pin) runs, with `supabase_vault` 0.3.1 ([its write-up](https://github.com/alexnodeland/lattice/blob/main/spikes/0943-egress-vault/README.md), [#1242](https://github.com/alexnodeland/lattice/pull/1242)). It found:

- **The API is as RFC-0011 assumes:** `vault.create_secret`, `vault.update_secret` and the `vault.decrypted_secrets` view. pgsodium is not needed: the image has it available but not installed.
- **The function holds.** A security-definer function owned by `postgres` reads the transaction's `lattice.tenant_id` and refuses another tenant's reference, or no tenant at all. It returned the caller's own secret, also after `update_secret`, to an application role that could neither select the view or the table nor call Vault's decrypt function.
- **But two roles read everything as shipped.**
  - `postgres` has `SELECT … WITH GRANT OPTION` on the view and may call the decrypt function.
  - `service_role` has both too. `postgres` can't revoke that, because `supabase_admin` made the grant. `supabase_admin`, the self-hosted superuser, can.
- **The key stays outside a dump.** The root key is a file, `/etc/postgresql-custom/pgsodium_root.key`, outside `PGDATA`. Neither `pg_dump` nor `pg_dumpall` contains it. The dump carries the ciphertext, and Vault's `name` and `description` in clear. Restored into a database with another key, the ciphertext fails (`invalid ciphertext`). With the key file copied across, it decrypts.
- **Local Supabase's key is public.** The CLI mounts the key file from its `db.root_key`. When that is unset, it uses one fixed key compiled into the CLI, and stackr's `supabase/config.toml` sets none.
- **stackr's production recipes run no Vault.**
  - The single-host recipe's Postgres is `postgres:17.11-alpine` with pgBackRest, which has no `supabase_vault` (checked).
  - The AWS recipe's is RDS PostgreSQL 17, which doesn't offer it (by its published extension list; not tested).

So "Supabase Vault … in the stack it already has" is true only of local and Supabase-hosted databases. The owner decided how to close the gap on 2026-10-31.

## Decision

- **Two adapters behind RFC-0011's `Secrets` port in 0.3.0,** each passing the same contract suite:
  - **Supabase Vault** (`lattice_core.secrets.supabase`, the `sql` extra), wherever the database is Supabase's (local Supabase and Supabase-hosted projects), and on the single-host recipe. There, stackr builds the `supabase_vault` extension, 0.3.x with no pgsodium, into `packages/stackr/deploy/host/postgres/Dockerfile`, beside pgBackRest.
  - **AWS Secrets Manager**, for the AWS recipe's tiers, since RDS has no Vault. Its metadata stays in grantr's tables under row-level security, as Vault's does. The secret's value lives in Secrets Manager, read with the task role's narrowest permission.
- **O7's copy command moves secrets between them.** It reads each value through the old adapter's port, writes it through the new one, rewrites the references, and then retires the old store. It never reads Vault's key.
- **For the Vault adapter, phase 3 must hold to these, which the spike showed are needed:**
  - **The application connects as a role of its own,** never `postgres` or `service_role`, each of which can read `vault.decrypted_secrets` as shipped. Where the database's owner can, which `supabase_admin` can self-hosted, the setup revokes `service_role`'s grants on the view, the table and Vault's functions. On a Supabase-hosted project, which keeps them, the service key stays with the operator.
  - **The tenant-checking security-definer function is the only read path.** The application's role has no privilege on the `vault` schema. The function checks the transaction's tenant in its own `WHERE`, because its owner bypasses row-level security. It runs with `search_path = ''`. Writes and rotation go through functions of the same kind.
  - **stackr sets a Vault root key per deployment**: `db.root_key` for local Supabase, and a mounted key file on the host recipe, from the deployment's secrets. It never uses the CLI's fixed key, and never a key generated in a container's writable layer, which a recreated container would replace.
  - **The key stays out of `pg_dump`, and out of the backups.** It is backed up apart from the database, and stackr's backup documentation says a dump can't be read without it.
  - **Nothing secret goes in Vault's `name` or `description`,** which are stored in clear.
- **The contract suite's isolation test** covers, on both databases (phase 3's exit criterion):
  - tenant-b's reference refused to tenant-a;
  - the application's role unable to select the view or the table, or to call Vault's decrypt function.

## Options considered

| Option | For | Against |
|---|---|---|
| **Vault where Postgres can hold it, Secrets Manager on AWS (chosen)** | Every recipe has a store in 0.3.0; Vault stays the default where it exists; AWS uses its own service | Two adapters to keep to one contract; the host recipe's image builds an extension |
| Vault only, as RFC-0011 has it | One adapter | No store on the host or AWS recipes |
| `supabase/postgres` as the host recipe's image | Vault included | A much larger image, Supabase's role layout, and the host recipe's pgBackRest setup reworked around it |
| A cloud KMS with envelope encryption in lattice | One adapter for every recipe | Lattice's own cryptography; Decision O4 chose against it |
| Secrets Manager everywhere | One adapter | Ties local and single-host deployments to AWS |

## Consequences

- Easier: every recipe stackr ships has a secrets store in 0.3.0, and a deployment can move between them with O7's command.
- Harder: Decision T7 moves forward. The second adapter is in 0.3.0, and it is AWS Secrets Manager, not RFC-0011's "one cloud adapter" in 0.3.x.
- Harder: the host recipe's image builds `supabase_vault`, which needs libsodium, `shared_preload_libraries` and `vault.getkey_script`, and it must be upgraded with the image. `scripts/check-config` holds it to the image compose pins.
- Harder: an operator must keep the Vault root key safe and backed up on its own. Losing it loses every secret.
- To revisit: GCP Secret Manager and HashiCorp Vault / OpenBao, still in 0.3.x behind the same port.

## Action items

1. [ ] `lattice_core.secrets.supabase`: the Vault adapter, its setup (own role, revokes, the functions) and the contract suite with the isolation test (RFC-0011 phase 3).
2. [ ] The AWS Secrets Manager adapter, through the same contract suite.
3. [ ] stackr: `supabase_vault` in the host recipe's Postgres image; a per-deployment root key for local Supabase (`db.root_key`) and the host recipe; the key's backup in the backup docs.
4. [ ] stackr: Secrets Manager in the AWS recipe, with the task role's permission.
5. [ ] O7's copy command between the two.
