# ADR-0053: Stored rules, under one fixed configuration

**Status:** Accepted; its `allow` folded into `authorize` by [ADR-0056](0056-access-asked-in-every-workspace-method.md)
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0006](0006-rules-as-typed-serializable-data.md), which left runtime rule management for after v0.1, and [ADR-0016](0016-tenants-and-workspaces-like-artifactr.md), under which every tenant's workspaces evaluate the same rules. Decided on [RFC-0003](../rfcs/0003-managing-rules-at-runtime.md).

## Context

Rules are typed, serializable data, but `Workspaces(storage, rules=[...])` took them at construction, so changing one meant a deploy. [stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md) needs rules a person accepts in chat to go live: the chat agent drafts a rule, a person accepts it, and relayr installs it in reflexr. That RFC requires a tenant's rules never listed to other tenants, a required throttle, no way to raise the depth limit, and only registered actions from an allowlist, never code.

A rule installed at runtime is behaviour that runs in the workspace, at the application's expense. Who may install one, and what it may do, has to be decided before anything is stored.

## Decision

- **A stored rule is the same `Rule`, kept in one workspace.** It belongs to the workspace it is installed in, like its cursor, state, runs and dead letters.
- **Stored rules are off unless `Workspaces` is given one fixed configuration:** `Workspaces(stored_rules=StoredRules(allow=..., actions={...}, namespaces={...}))`. Without it, every change is `forbidden`.
- **`allow(tenant_id, workspace_id, actor, change) -> bool`** is shaped like `authorize`, with the `RuleChange`: which command, which rule, and the new rule if there is one. The surfaces ask `authorize`, then `allow`. A refusal is `forbidden`, as is a change to a code rule's name.
- **`actions` is the only allowlist,** each action mapped to its params model, or `None` ([ADR-0052](0052-typed-action-parameters.md)). The reactor confirms when it is built that each is registered and declares that model.
- **`namespaces` are the rule namespaces stored rules may use** ([ADR-0051](0051-qualified-rule-names.md)). `reflexr` is reserved, and `Workspaces` refuses a code rule in one of them.
- **Everything else is a constant in core,** the same for every tenant:

| Limit | Value |
|---|---|
| `throttle` | Required, at most 60 firings an hour |
| Scope fields, predicates, the `matches` operator | None |
| `start` | `now` |
| `enabled`, `ordering`, `on_dead_letter` | `true`, `"none"`, `"continue"` |
| `retry.max_attempts` | At most 5 |
| `timeout` | Required, at most 5 minutes |
| Windows: `within`, a dedupe window, a throttle's `per` | At most 1 day |
| `description` | At most 2,000 characters |
| The rule's JSON | At most 16 KiB |
| Provenance | At most 4 KiB |
| Active stored rules per workspace | At most 50 |

- **`check_stored(rule, config)` is pure, beside `Rule.check`,** and lists every problem with a rule against the configuration and the constants; `check_provenance` checks a change's provenance. Installing and updating run them all and report every problem together as `validation_failed`, so a draft can be checked the same way before it is proposed. The count of active rules is checked in the change's transaction.
- **A stored rule watches what a code rule may:** any event type its `Workspaces` accepts, resolved in that `Workspaces`' registry.

With no scope fields, the one throttle bounds the whole rule. `matches` is refused because Python's `re` has no timeout and evaluation holds the workspace's lock. Usage limits stay on the registered action, the tenant's gateway budget applies through `[litellm]`, and the depth limit is `Workspaces(max_depth=)`, which no rule field can raise.

## Options considered

### Configuration and authorization

| Option | For | Against |
|---|---|---|
| **One fixed `StoredRules`: `allow`, the actions and the namespaces, with every other limit a constant in core (chosen)** | One place, one hook shaped like `authorize`, and a pure `check_stored` for drafts | The same limits for every tenant |
| A per-change policy returning `RuleLimits` | Limits per tenant, plan or installer | A second, larger hook, for variation nothing needs yet |
| Reuse `authorize` | Nothing new | Anyone who may use a workspace could install behaviour that runs in it |

### Watching

| Option | For | Against |
|---|---|---|
| **Any event type the workspace accepts, as for code rules (chosen)** | Nothing new | A chat rule may watch reflexr's facts |
| Namespaces the configuration grants | Least privilege | A list to keep, with no present need |
| The namespaces the tenant may publish into | One policy | Watching isn't publishing: chat rules watch `artifactr:` types, which only relayr publishes |

## Consequences

- Easier: a rule goes live without a deploy, and only code the application registered ever runs.
- Easier: relayr's artifact type checks a draft with `Rule.check` and `check_stored` before anyone proposes it.
- Harder: tenants get behaviour that runs. It is bounded by the allowlist, the constants, review and a configuration that is off by default, but it is a new surface to defend.
- Harder: stored rules can't pause, order their runs, or throttle per scope, and every tenant has the same limits.
- To revisit: limits or namespace grants per tenant or installer, and grants of watched namespaces, when something needs them. lattice's [RFC-0001](../../rfcs/0001-grantr-identity-and-access.md) plans to fold `allow` into a widened `authorize`.

## Action items

1. [x] `StoredRules`, `RuleChange`, `check_stored`, `check_provenance` and the constants (alexnodeland/reflexr#86).
2. [x] `Workspaces(stored_rules=)`, and the reactor's check of the allowlisted actions (alexnodeland/reflexr#88).

## Amendment (2026-10-12): `allow` is folded into `authorize`

[ADR-0056](0056-access-asked-in-every-workspace-method.md) removes `StoredRules.allow` and `RuleChange`. Installing, updating, archiving and replaying a stored rule are commands like any other, which the widened `authorize` hears with the rule's name in `Access.rule`. The concern behind "Reuse `authorize`" above, that anyone who may use a workspace could install behaviour in it, no longer holds: the hook hears the action, so an application, or grantr's workspace `admin` role, grants rule management apart from using the workspace. `StoredRules` keeps `actions` and `namespaces`, what a stored rule may do; without it, every change is still `forbidden`.
