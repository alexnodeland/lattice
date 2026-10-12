# Architecture

Decisions are recorded in [`adr/`](adr/README.md), and the plan that builds grantr in [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). The design is [lattice RFC-0001](../rfcs/0001-grantr-identity-and-access.md). This page describes what exists: grantr's core, its storage port and in-memory adapter, and the hooks, which are phase 2 of the plan.

## What grantr is

grantr decides who may do what in a tenant. artifactr and reflexr ask it, through hooks typed in the libraries, before every command and read; stackr's template wires the two together. grantr imports neither library, and neither imports it: actions cross as strings, and the libraries' `Access` and actors reach grantr structurally.

## Layers

| Package | Holds | May import |
|---|---|---|
| `grantr.core` | The model and its types, grantr's catalog, the built-in roles, the rule every check follows, the audit events, and service principal keys. No I/O and no async | pydantic |
| `grantr.grants` | `Grants`, with its checks, the hooks and the commands that change access; the storage port, `Storage`; and `InMemoryStorage` | `grantr.core` |

`tests/test_layering.py` holds each package to its column, and keeps I/O out of the core.

## The model

| Concept | What it is |
|---|---|
| **Subject** | Who a check is about: a `User`, a `ServicePrincipal`, a `RulePrincipal` (a reflexr rule, by its workspace and name) or the `Agent`, which holds nothing. Frozen models, discriminated by `kind` |
| **Grantee** | Who a grant names: any subject but the agent, or a `Group` |
| **Resource** | The deployment, a tenant, a workspace, or a thread, artifact or rule in a workspace. It names no tenant: the tenant is the check's |
| **Role** | A named set of actions: built in, or a tenant's own (`Role`) |
| **Grant** | A role, on a resource, to a grantee, in a tenant; a grant on the deployment is in none |
| **Membership** | A user's tenant roles, from the grants made to them on the tenant |

### The check

A subject holds an action on a resource when a grant to it, or to a group it is in, names a role with that action on the resource or on one it is in. An item is in its workspace and a workspace in the tenant; a tenant is not in the deployment, so an operator holds nothing inside a tenant until they grant themselves a role there. Everything else is refused: an action in no catalog, the agent acting for no one, a principal with no grant that applies, and a store that can't be read.

### Built-in roles

The application hands `Grants` each library's catalog, its `ACTIONS`, and grantr adds its own. The built-in roles are defined over them ([ADR-0011](adr/0011-built-in-roles-over-the-catalogs.md)):

| Role | On | Holds |
|---|---|---|
| `operator` | the deployment | `grantr:create_tenant` and `grantr:grant_operator` |
| `owner` | a tenant | every action in every catalog but the operator's |
| `admin` | a tenant | the owner's, but `grantr:delete_tenant` |
| `member` | a tenant | nothing: it makes a user or service principal a member |
| `admin` | a workspace | every library action, and `grantr:grant`, `revoke` and `restrict` |
| `editor` | a workspace, thread, artifact or rule | a viewer's, and the commands that post, create, edit, propose, archive, resolve proposals and operate runs |
| `viewer` | a workspace, thread, artifact or rule | every `read_` action, every `open`, and giving feedback |

A custom role is a tenant's own set of actions, granted wherever `editor` can be. It holds only actions a workspace's admin holds, and can't take a built-in role's name.

## Commands

`Grants` holds the commands that change access, each made `by` a subject ([ADR-0010](adr/0010-commands-bounded-by-what-their-maker-holds.md)):

| Command | Requires |
|---|---|
| `first_operator` | No operator yet |
| `grant_operator`, `revoke_operator` | `grantr:grant_operator` on the deployment |
| `create_tenant` | `grantr:create_tenant` on the deployment; its owner is made a member and an owner |
| `delete_tenant` | `grantr:delete_tenant` |
| `add_member`, `remove_member` | `grantr:add_member`, `grantr:remove_member` |
| `define_group`, `delete_group` | `grantr:manage_groups` |
| `define_role`, `delete_role` | `grantr:define_role` |
| `grant`, `revoke` | `grantr:grant`, `grantr:revoke` on the resource; an operator granting themselves, or anyone revoking their own grant, needs neither |
| `issue_key`, `revoke_key` | `grantr:issue_key`, `grantr:revoke_key` |
| `audit` | `grantr:read_audit`, or `grantr:grant_operator` for the deployment's log |

- **No one gives more than they hold.** A command that gives or takes access is refused unless its maker holds every action it gives or takes, where it applies: a grant's role on its resource; each grant a removed member loses; the grants a group's members gain or lose; and the grants a key acts with, when it is issued or revoked. A custom role needs no bound: whoever may define one holds every action it can hold.
- **Membership is the `member` grant.** `add_member` and `remove_member` are its only paths; roles are granted only to members, and groups hold only members. Removing a member takes its grants, its places in groups and its keys.
- **An operator enters a tenant by granting themselves a role,** which makes them a member first; both are in the tenant's audit log ([ADR-0014](adr/0014-an-operator-enters-a-tenant-by-granting-themselves.md)).
- **A tenant keeps an owner:** revoking, removing or deleting its last `owner` grant is refused.
- **Each command is one transaction:** its checks, its change, and one audit entry. A command that raises changes nothing.
- **A refusal comes first,** before anything is looked up, so it says nothing about what exists.

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

`hidden` hides nothing yet: no item can be restricted until phase 5.

## Storage

`Storage` is the port ([ADR-0013](adr/0013-transactions-by-tenant-and-one-audit-log.md)), and `InMemoryStorage` its first adapter; phase 3 adds the SQL one.

- **A transaction is in one tenant,** or on the deployment, and serialized with every other there. The in-memory adapter runs one at a time, on a copy it keeps only if the block exits normally.
- **Every read is in one tenant, but two:** `tenant_grants` and `key` span tenants, since they are asked before the tenant is known.
- **`grants` answers for a grantee and its groups,** optionally on some resources: the one query a check makes. `has` looks up one grant, for membership and duplicates.
- **grantr knows a workspace, thread, artifact or rule once a grant names it,** or something in it, and `resources` lists those. A check writes nothing ([ADR-0015](adr/0015-a-check-writes-nothing.md)).

The contract test, `tests/grants/test_contract.py`, runs every behaviour on this page against each adapter that `tests/grants/conftest.py` lists.
