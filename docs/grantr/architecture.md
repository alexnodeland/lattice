# Architecture

Decisions are recorded in [`adr/`](adr/README.md), and the plan that builds grantr in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). The design is [lattice RFC-0001](../rfcs/0001-grantr-identity-and-access.md). This page describes what exists: grantr's core, its storage port with in-memory and SQL adapters, the hooks, the admin API and telemetry, which are phases 2 and 3 of the plan.

## What grantr is

grantr decides who may do what in a tenant. artifactr and reflexr ask it, through hooks typed in the libraries, before every command and read; stackr's template wires the two together. grantr imports neither library, and neither imports it: actions cross as strings, and the libraries' `Access` and actors reach grantr structurally.

## Layers

| Package | Holds | May import |
|---|---|---|
| `grantr.core` | The model and its types, grantr's catalog, the built-in roles, the rule every check follows, the audit events, and service principal keys. No I/O and no async | pydantic |
| `grantr.telemetry` | The check counter, slow checks' spans and the audit log's copy, through the OpenTelemetry API | `grantr.core`, the OpenTelemetry API |
| `grantr.grants` | `Grants`, with its checks, the hooks, the commands that change access and the lists an admin reads; the storage port, `Storage`; and `InMemoryStorage` | `grantr.core`, `grantr.telemetry`, the OpenTelemetry API |
| `grantr.sql` | `SqlStorage`, its tables and Alembic migrations, and `create_sqlite_engine`. The `sql`, `sqlite` and `postgres` extras | `grantr.core`, pydantic, SQLAlchemy, Alembic |
| `grantr.testing` | `matrix`, every role against every action, as a table to commit | `grantr.core` |
| `grantr.fastapi` | `grantr_router`, the admin API, and its OpenAPI document. The `fastapi` extra | `grantr.core`, `grantr.grants`, FastAPI |

`tests/test_layering.py` holds each package to its column, and keeps I/O out of the core.

## The model

| Concept | What it is |
|---|---|
| **Subject** | Who a check is about: a `User`, a `ServicePrincipal`, a `RulePrincipal` (a reflexr rule, by its workspace and name) or the `Agent`, which holds nothing. Frozen models, discriminated by `kind` |
| **Service principal's id** | Not empty, and with no `:`, `~` or whitespace, so it can't pass for the libraries' own actors, such as relayr's code rules, `reflexr:<rule>` ([ADR-0028](adr/0028-a-principals-id-cant-pass-for-the-libraries-actors.md)) |
| **Grantee** | Who a grant names: any subject but the agent, or a `Group` |
| **Resource** | The deployment, a tenant, a workspace, or a thread, artifact or rule in a workspace. It names no tenant: the tenant is the check's |
| **Role** | A named set of actions: built in, or a tenant's own (`Role`) |
| **Grant** | A role, on a resource, to a grantee, in a tenant; a grant on the deployment is in none |
| **Membership** | A user's tenant roles, from the grants made to them on the tenant |

### The check

A subject holds an action on a resource when a grant to it, or to a group it is in, names a role with that action on the resource or on one it is in. An item is in its workspace and a workspace in the tenant; a tenant is not in the deployment, so an operator holds nothing inside a tenant until they grant themselves a role there. Everything else is refused: an action in no catalog, the agent acting for no one, a principal with no grant that applies, and a store that can't be read.

A restricted thread or artifact is the exception to the chain ([ADR-0024](adr/0024-who-sees-a-restricted-item.md)): on it, a grant on its workspace or tenant holds only if its role holds `grantr:restrict`, as the workspace's `admin` and the tenant's `owner` and `admin` do. A grant on the item itself holds as ever.

### Built-in roles

The application hands `Grants` each library's catalog, its `ACTIONS`, and grantr adds its own. The built-in roles are defined over them ([ADR-0011](adr/0011-built-in-roles-over-the-catalogs.md), [ADR-0019](adr/0019-runtime-actions-and-the-application-role.md), [ADR-0020](adr/0020-the-rule-role.md)). No person's role holds the bookkeeping: `artifactr:claim_thread`, and `save_cursor` and `read_cursors` in both libraries.

| Role | On | Holds |
|---|---|---|
| `operator` | the deployment | `grantr:create_tenant`, `grantr:grant_operator`, and portalr's `portalr:read_deployment` |
| `application` | the deployment, holding in every tenant | the bookkeeping, `artifactr:record`, `reflexr:publish`, `reflexr:checkpoint_run`, its evaluators' feedback, what its code rules write in artifactr through relayr (`propose_change`, `post_message`, `create_artifact`, `edit_artifact`, `create_thread`), the stored rules relayr installs for people who may (`install_rule`, `update_rule`, `archive_rule`, [ADR-0027](adr/0027-the-application-installs-the-rules-people-accept.md)), and every `open` and read but portalr's admin reads ([ADR-0025](adr/0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md)) |
| `owner` | a tenant | every action in every catalog but the operator's, the deployment's reads and the bookkeeping; portalr's `read_telemetry` and `read_spend` included |
| `admin` | a tenant | the owner's, but `grantr:delete_tenant` |
| `member` | a tenant | `artifactr:read_workspaces`: listing the tenant's workspaces, which artifactr filters by what the caller may open; it makes a user or service principal a member |
| `admin` | a workspace | every library action but the bookkeeping, and `grantr:grant`, `revoke` and `restrict` |
| `editor` | a workspace, thread, artifact or rule | a viewer's, and the commands that post, create, edit, propose, archive, resolve proposals, record a turn, and stop and operate runs |
| `viewer` | a workspace, thread, artifact or rule | every `read_` action but the cursors, every `open`, and giving feedback |
| `rule` | a workspace | `reflexr:open`, `reflexr:publish`, `reflexr:checkpoint_run`, `reflexr:read_events` and `reflexr:read_runs`: a stored rule's runs; and `artifactr:open` and `artifactr:post_message`, for their notices through relayr ([ADR-0029](adr/0029-a-stored-rule-posts-notices-as-itself.md)) |

`application` is the one deployment role that holds in every tenant, and only the application's own service principal holds it: `Grants(application=...)` names it, and `Grants.bootstrap()` grants it at start, and revokes it from any other holder. That principal is no tenant's member, and no key of it is answered, so no tenant can borrow it. A catalog that names a library's actions must name all its bookkeeping, or `Catalog.of` refuses it. `grantr.testing.matrix(catalogs, roles)` prints every role against every action, for an application to commit and review.

A custom role is a tenant's own set of actions, granted wherever `editor` can be. It holds only actions a workspace's admin holds, and can't take a built-in role's name.

## Commands

`Grants` holds the commands that change access, each made `by` a subject ([ADR-0010](adr/0010-commands-bounded-by-what-their-maker-holds.md)):

| Command | Requires |
|---|---|
| `first_operator` | No operator yet |
| `bootstrap` | The application's configured principal: grants it `application`, and revokes it from any other |
| `served_tenants` | No one: every tenant, for the deployment's own in-process tools; no surface reaches it |
| `provision_tenant` | The deployment's own tools, in process: a new tenant with its owner, and the admins it lacks ([ADR-0021](adr/0021-the-deployments-own-tools.md)) |
| `grant_operator`, `revoke_operator` | `grantr:grant_operator` on the deployment |
| `create_tenant` | `grantr:create_tenant` on the deployment; its owner is made a member and an owner |
| `delete_tenant` | `grantr:delete_tenant` |
| `add_member`, `remove_member` | `grantr:add_member`, `grantr:remove_member` |
| `define_group`, `delete_group` | `grantr:manage_groups` |
| `define_role`, `delete_role` | `grantr:define_role` |
| `grant`, `revoke` | `grantr:grant`, `grantr:revoke` on the resource; an operator granting themselves, or anyone revoking their own grant, needs neither |
| `issue_key`, `revoke_key` | `grantr:issue_key`, `grantr:revoke_key` |
| `restrict` | `grantr:restrict` on the thread or artifact; it sets or clears its restricted flag |
| `audit` | `grantr:read_audit`, or `grantr:grant_operator` for the deployment's log |

- **No one gives more than they hold.** A command that gives or takes access is refused unless its maker holds every action it gives or takes, where it applies: a grant's role on its resource; each grant a removed member loses; the grants a group's members gain or lose; and the grants a key acts with, when it is issued or revoked. A custom role needs no bound: whoever may define one holds every action it can hold.
- **Membership is the `member` grant.** `add_member` and `remove_member` are its only paths; roles are granted only to members, and groups hold only members. Removing a member takes its grants, its places in groups and its keys.
- **An operator enters a tenant by granting themselves a role,** which makes them a member first; both are in the tenant's audit log ([ADR-0014](adr/0014-an-operator-enters-a-tenant-by-granting-themselves.md)).
- **A tenant keeps an owner:** revoking, removing or deleting its last `owner` grant is refused.
- **Each command is one transaction:** its checks, its change, and one audit entry. A command that raises changes nothing.
- **A refusal comes first,** before anything is looked up, so it says nothing about what exists.

## Lists

An admin reads each list with the action of the command that changes it ([ADR-0017](adr/0017-the-admin-api.md)): `members` with `grantr:add_member`, `groups` with `grantr:manage_groups`, `roles` with `grantr:define_role`, `grants_in` with `grantr:grant` on the tenant or a workspace, `keys` with `grantr:issue_key`, `restrictions` with `grantr:restrict` on the workspace, and `tenants` with `grantr:create_tenant`.

## Keys

A service principal's key is `grantr_sk_<id>_<secret>`: an 8-byte public id and 32 random bytes, in hex. `issue_key` returns it once; grantr stores the id, the tenant, the principal and a SHA-256 digest of the secret. `authenticate` finds a key by its id and compares digests in constant time, and answers with the key's tenant and principal, so a key reaches only its own tenant.

## The audit log

Every command appends one typed event, such as `Granted` or `MemberRemoved`, to one append-only log for the deployment. Each entry has its sequence number, the time, the tenant it changed (`None` for the operators) and who made it (`None` for the first operator). A tenant's entries are read in order, paged by sequence number. A key's secret and digest are never in it, and refusals aren't recorded.

## The hooks

`Grants.hooks(subject_of)` returns the libraries' `authorize` and `hidden` hooks ([ADR-0012](adr/0012-every-item-an-access-names-and-hooks-typed-by-actor.md)). `subject_of` is the application's map from a library's actor to a subject. `authorize` checks the access's action on what it is about:

| The access names | Checked on |
|---|---|
| No workspace | The tenant |
| A thread, an artifact or a rule | Each of them, all of which must allow it |
| None of them | The workspace |

`hidden` returns the restricted threads and artifacts in a workspace on which the actor's subject holds nothing: the check's rule above. The application's own principal sees everything, and the agent acting for no one no restricted item.

## Storage

`Storage` is the port ([ADR-0013](adr/0013-transactions-by-tenant-and-one-audit-log.md)), with two adapters: `InMemoryStorage`, and `SqlStorage`, below.

- **A transaction is in one tenant,** or on the deployment, and serialized with every other there. The in-memory adapter runs one at a time, on a copy it keeps only if the block exits normally.
- **Every read is in one tenant, but three:** `tenant_grants` and `key` span tenants, since they are asked before the tenant is known, and `tenants` lists them for operators.
- **`grants` answers for a grantee and its groups,** optionally on some resources: the grants query a check makes. `has` looks up one grant, for membership and duplicates.
- **grantr knows a workspace, thread, artifact or rule once a grant names it,** or something in it, or once a thread or artifact is restricted, and `resources` lists those, leaving out restricted items the subject can't see. A check writes nothing ([ADR-0015](adr/0015-a-check-writes-nothing.md)).

The contract test, `tests/grants/test_contract.py`, runs every behaviour on this page against memory, SQLite and PostgreSQL. The PostgreSQL tests run when `GRANTR_TEST_POSTGRES_URL` is set, as CI sets it, and `moon run grantr:pg-up` starts a database.

### SQL

`SqlStorage` keeps grantr in the application's database, in eight `grantr_`-prefixed tables, with Alembic migrations that record their version in `grantr_alembic_version` ([ADR-0016](adr/0016-the-sql-adapter.md)).

- **A subject and a resource are stored in typed columns,** their kind, workspace and id, with an empty string for a part they don't have. A grant's primary key, its tenant, resource, subject and role, is the index a check reads, and every other query has an index that leads with its filter.
- **A check is one query, one more when a grant names a custom role, and one more, by primary key, on a thread or artifact** when a grant around it applies; the subject's groups are a subquery of the first.
- **The deployment is the tenant `~deployment`,** which no tenant id can be: a tenant id is not empty and has no `~`.
- **A transaction locks its tenant's row** in `grantr_tenants`, inserting it first if needed; the row's `live` flag says whether the tenant exists.
- **The audit log's sequence numbers are the database's.** A tenant's transactions run one at a time, so its entries are numbered in the order they commit.
- **Every database call is awaited to its end,** even when its caller is cancelled, as in the libraries' SQL storage.
- **Row-level security is an option** ([ADR-0026](adr/0026-row-level-security-under-the-scoping.md)). With `row_level_security=True`, each transaction names its tenant, or `~deployment`, in `lattice.tenant_id`, and the policies migration 0003 creates on PostgreSQL keep every command to its tenant's rows, and let it read the deployment's grants and group members besides. `migrate(application_role=...)` grants a role that owns nothing the tables. `tenant_grants`, `key` and `tenants`, which span tenants, go to `across_tenants`, an engine as the tables' owner, and nothing else does.

## The admin API

`grantr_router(grants, resolve_actor=...)` is the admin API, mounted at `/grantr/v1` ([ADR-0017](adr/0017-the-admin-api.md)). `resolve_actor` returns a `Caller`: the subject, and, for a key, its one tenant, which the router holds every request to.

| Path | What it does |
|---|---|
| `GET /me` | With `X-Tenant`, the caller's roles there and the workspaces they can open; without, their memberships |
| `POST /checks` | A batch of up to 100 `{action, resource}` questions, answered in order |
| `GET`, `POST /tenants`; `DELETE /tenants/{tenant}` | List, create and delete tenants |
| `PUT`, `DELETE /operators/{user}` | Grant and revoke the operator role |
| `GET /audit`, `GET /tenants/{tenant}/audit` | The deployment's and a tenant's audit log, paged by `after_seq` |
| `/tenants/{tenant}/members`, `/groups`, `/roles`, `/grants`, `/revocations`, `/keys`, `/restrictions` | The lists and commands above |

Refusals keep the libraries' shapes, `{"type", "message"}`: 401 `unauthorized` without a caller, 403 `forbidden`, 422 `invalid`, and 400 `tenant_required` when a caller in several tenants names none. Its OpenAPI document is committed in `packages/grantr/schemas/grantr.openapi.json`; `moon run grantr:schema` regenerates it, and a test fails when it drifts.

## Telemetry

grantr records through the OpenTelemetry API only ([ADR-0018](adr/0018-telemetry-through-the-api.md)): the `grantr.checks` counter, by action (`unknown` for one in no catalog), outcome and reason; a `grantr.check` span for each check slower than `slow_check`; and each audit entry, logged as JSON on the `grantr.audit` logger once its change commits.

