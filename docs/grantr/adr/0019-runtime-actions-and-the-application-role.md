# ADR-0019: Runtime actions, and the application role

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0009](0009-a-deployment-wide-operator-role.md), whose deployment role no longer stays out of every tenant, and [ADR-0011](0011-built-in-roles-over-the-catalogs.md), whose roles change.

## Context

The libraries' catalogs (lattice RFC-0001's phase 1) name actions no person takes: the runner claims threads, the log's consumers keep cursors, a rule's run checkpoints, and a turn records that it started. The runner, the mirrors and the reactor act as the application, through `SystemActor`, and the application's code rules run as it too. Under ADR-0011's prefix rule, `read_cursors` would land in `viewer`, and a workspace's `admin` would hold the bookkeeping too.

## Decision

- **No person's role holds the bookkeeping:** `artifactr:claim_thread`, and `save_cursor` and `read_cursors` in both libraries, are left out of every role a person is granted, whatever their prefix.
- **`editor` gains `artifactr:stop_run`, and `artifactr:record`,** which a turn an editor's message starts asks as them. A viewer can't start a turn, and doesn't hold it. `reflexr:checkpoint_run` stays out of `viewer` and `editor`; a workspace's `admin` holds it.
- **A built-in `application` role,** granted on the deployment, holds the runtime: the bookkeeping, `artifactr:record`, `reflexr:publish` and `reflexr:checkpoint_run`, the libraries' `give_feedback` for its evaluators, and every `open` and read. It holds none of a person's other commands.
- **`application` is the one deployment role that holds in every tenant,** and only for the principal `Grants` is made with: a check for that principal also looks up its grant, one indexed lookup. `operator` still puts no one inside a tenant.
- **No tenant can borrow that identity.** Service principals aren't scoped to a tenant, so a tenant's admin could otherwise add a principal of the same id and key it. The application's principal is no tenant's member (`add_member` refuses it), `authenticate` answers no key of it, and the exception holds for the configured principal alone.
- **`Grants.bootstrap()` is the only path to the role.** The application calls it as it starts: it grants the role to its principal if it hasn't it, and revokes it from any other holder, as when the principal is renamed, each in an audit entry made by no one. Replicas starting together grant it once, since the deployment's changes run one at a time. No operator grants it, and `grant` refuses it anywhere: the role is the application's configuration, not a decision anyone in the running system makes, and a grant an operator could give would be the identity a tenant must never borrow.

## Options considered

| Option | For | Against |
|---|---|---|
| **`application` on the deployment, holding in every tenant (chosen)** | One grant for every tenant, made once, at start | An exception to the rule that the deployment's roles stay out of tenants |
| A grant per tenant | No exception | Every new tenant needs one, or the application stops working in it |
| Tenant `admin` for the application | No new role | Every person's command, and grantr's, in every tenant |
| **Bootstrap for the configured principal, and nothing else (chosen)** | No operator is needed for a new deployment to run its agents, and no one can give the role away | The application's configuration names its principal |
| An operator may grant it too | Flexible | A second path to the most powerful runtime identity, which the configuration doesn't name |

## Consequences

- Easier: a new tenant works the moment it is created, and people's roles say only what people do.
- Harder: a check for a service principal is two lookups, and the matrix snapshot shows `application` beside the people's roles.
