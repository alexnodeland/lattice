# ADR-0056: Access asked in every workspace method

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0044](0044-surfaces.md) put authorization within a tenant behind one hook, `authorize(tenant_id, workspace_id, actor)`, which the router and `ReflexrMcp` each took and passed to `Workspaces.open`. [ADR-0053](0053-stored-rules-one-fixed-configuration.md) gave stored rules a second hook, `StoredRules.allow`, asked after it with the `RuleChange`. Three gaps followed:

- **The hook never heard the action.** Anyone who could use a workspace could operate its runs and replay its rules; the security guide told applications to check commands in their own routes.
- **Two hooks for one question.** "May this actor install this rule here?" was split between `authorize` and `allow`, and a surface could be given one without the other.
- **The reads across a tenant skipped it.** `GET /rules`, `GET /schedules` and `list_rules` named no workspace, so [ADR-0016](0016-tenants-and-workspaces-like-artifactr.md)'s amendment let every authenticated client read them, and an application that must hide them had to unmount the routes.

[lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md) widens the hook so it hears the action, asks it for every command and read, and lets grantr answer it. Its phase 1 is this change; artifactr's [ADR-0056](../../artifactr/adr/0056-access-asked-in-every-workspace-method.md) is its twin.

## Decision

- **`Access`, `Authorize`, `OnOpen` and `ACTIONS`** live in `reflexr.workspace`:
  - `Access(action, rule=None)` is what an actor is about to do. reflexr has no threads or artifacts, so it has `rule` in their place: a rule command's rule, or the rule a read names.
  - `Authorize = Callable[[TenantId, WorkspaceId | None, Actor, Access], Awaitable[bool]]`.
  - `OnOpen = Callable[[TenantId, WorkspaceId], Awaitable[None]]`.
  - `ACTIONS` is the complete catalog, as `reflexr:<name>`. A command's action is its `type` (`reflexr:retry_run`, `reflexr:install_rule`), a read's is `read_` and what it reads (`reflexr:read_runs`, `reflexr:read_dead_letters`, `reflexr:read_rules`, `reflexr:read_schedules`), and opening a workspace is `reflexr:open`. An action's progress is `reflexr:checkpoint_run`, and a consumer's place in the log `reflexr:save_cursor` and `reflexr:read_cursors`.
- **`Workspaces` holds the hooks:** `Workspaces(storage, ..., authorize=, on_open=)`. `Workspaces.open`, `reflexr_router` and `ReflexrMcp` no longer take `authorize`.
- **Every public `Workspace` method asks first,** as the handle's actor, through `Workspace.check(access)`, which raises `Forbidden` (`"reflexr:retry_run is refused in this workspace"`). `publish` asks through `publish_many`. `rule_statuses` and `schedule_statuses` read storage themselves, so each asks once, for `reflexr:read_rules` and `reflexr:read_schedules`; a rule status's dead-letter count and lag are read under `reflexr:read_rules`, not `reflexr:read_dead_letters` and `reflexr:read_events`.
- **The reads across a tenant go through `Workspaces`:** `rules_for(tenant_id, actor=)` and `schedules_for(tenant_id, actor=)` ask with no workspace (`"reflexr:read_rules is refused in this tenant"`). `GET /rules`, `GET /schedules` and `list_rules` call them. This amends ADR-0016's amendment: an application can now keep rule and schedule definitions from some members.
- **`StoredRules.allow` is folded in, and `RuleChange` removed.** Installing, updating, archiving and replaying a rule are commands like any other, which `authorize` hears with the rule's name. `StoredRules` keeps `actions` and `namespaces`: what a stored rule may do, not who may store it. Without `StoredRules`, a change is still `forbidden`, as is one to a code rule's name, after the hook is asked.
- **Opening asks `reflexr:open`, then calls `on_open`.** Its callees are idempotent, so a permission check has no side effects.
- **The reactor's own work stays beneath the hook.** Evaluating rules, claiming runs, ticking schedules and reading a workspace's rules (`Workspaces.rules_in`) work on storage, not on a handle, as they always have. A run's action opens its workspace as its rule's `AgentActor`, which every method then asks as.
- **A run that `authorize` refuses fails for good.** An action's run opens its workspace as its rule's `AgentActor`; a refusal there, or of anything the action then does (`reflexr:publish`, `reflexr:checkpoint_run`), fails the attempt permanently, with the reason `forbidden`, since a retry would be refused too, and spoils no other run of the batch. An `on_open` that raises fails the attempt, to retry.
- **The MCP server follows a workspace's log as itself,** `SystemActor(name="mcp")`, not as the client whose tool call first opened it.
- **A cursor saved with a command** is covered by that command's check; only `save_cursor` asks `reflexr:save_cursor`.
- **A WebSocket that may not read the log** is closed with 4403 before `welcome`.
- **A permission-matrix test** (`tests/test_access.py`) lists every public `Workspace` method with the `Access` it asks for, the reads across a tenant, and every REST route, WebSocket command, and MCP tool and resource with what its caller is asked for. It calls each with a hook that records what it is asked. A method or surface missing from the tables, an action outside `ACTIONS`, or an action in `ACTIONS` nothing asks for fails it. What asks nothing on purpose (`as_actor`, `caused_by`, `check`, `execute`, `rules_in`, and listing MCP's tools and resource templates) is listed with its reason.

## Options considered

### Option A: one hook, asked in every method, with the rule in `Access` (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one `check` call per method, and `allow` deleted |
| Coverage | Every surface and in-process call; the reads across a tenant too |

**Pros:** one question, one hook, one place per method; grantr can grant rule management to a role.
**Cons:** every application's `authorize` changes shape.

### Option B: keep `allow` beside a widened `authorize`

Rejected by the RFC (D1): three hooks in reflexr, and a surface can forget one.

### Option C: leave the reads across a tenant open

**Pros:** no workspace-less check to explain.
**Cons:** rule definitions can't be hidden from some members, and the matrix would carry a hole by design.

## Trade-off analysis

Folding `allow` into `authorize` loses nothing it said: the command is the action, and the rule its `Access.rule`. The new rule itself is no longer handed to the hook; what it may do is `StoredRules`' allowlists and core's limits, which the hook was never meant to judge. The cost of a check per method is one hook call, which grantr answers with one indexed query.

## Consequences

- Easier: one hook decides every command and read, and who may manage rules is a grant like any other: a workspace admin's, in grantr's built-in roles.
- Easier: an application can hide rule and schedule definitions from some members.
- Harder: every application's `authorize` takes the `Access` and moves to `Workspaces`, and `StoredRules(allow=...)` is gone: breaking changes, released as a minor version before 1.0 ([lattice ADR-0006](../../adr/0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)).
- Harder: a subscription is checked when it opens; events keep flowing after a revocation until it closes.
- Harder: with `RuleChange.spec` gone, the hook no longer sees the rule being installed, so a policy can't refuse a rule by its content; only `StoredRules`' allowlists and core's limits judge that.
- Revisit: the rule a `retry_run`, `skip_run` or `cancel_run` is about, which needs the run loaded first, when grants on rules need it.

## Action items

1. [x] `Access`, the widened `Authorize`, `OnOpen` and `ACTIONS`, held by `Workspaces`.
2. [x] A check in every `Workspace` method; `rules_for` and `schedules_for` with no workspace.
3. [x] `StoredRules.allow` and `RuleChange` removed.
4. [x] The permission-matrix test.
5. [ ] grantr answers the hook (lattice RFC-0001, phases 2 to 4).
