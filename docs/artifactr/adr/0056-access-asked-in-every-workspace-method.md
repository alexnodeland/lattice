# ADR-0056: Access asked in every workspace method

**Status:** Accepted; amended by [ADR-0058](0058-a-tenants-workspaces-listed-by-what-each-actor-may-open.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0048](0048-surfaces-over-the-runner.md) put authorization within a tenant behind one hook, `authorize(tenant_id, workspace_id, actor)`, which the router and `ArtifactrMcp` each took and passed to `Workspaces.open`. That hook had three gaps:

- **It never heard the action.** It was asked once, when a workspace was opened, so a role such as "viewer" could not be kept from editing. The security guide told applications to check commands in their own routes.
- **Each surface took it separately.** An application could give the router one hook and the MCP server another, or none, and in-process calls, the agent's tools among them, were never asked.
- **It had side effects.** The template's only hook started the workspace's feedback mirror and returned `True`, so a permission check did work.

[lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md) widens the hook so it hears the action, asks it for every command and read, and lets grantr answer it. Its phase 1 is this change.

## Decision

- **`Access`, `Authorize`, `OnOpen` and `ACTIONS`** live in `artifactr.workspace`:
  - `Access(action, thread_id=None, artifact_id=None)` is what an actor is about to do. It has no `rule`; reflexr's has.
  - `Authorize = Callable[[TenantId, WorkspaceId | None, Actor, Access], Awaitable[bool]]`. artifactr always names the workspace; the `None` is for reads that span a tenant, which reflexr has.
  - `OnOpen = Callable[[TenantId, WorkspaceId], Awaitable[None]]`.
  - `ACTIONS` is the complete catalog, as `artifactr:<name>`. A command's action is its `type` (`artifactr:edit_artifact`), a read's is `read_` and what it reads (`artifactr:read_artifacts`), and opening a workspace is `artifactr:open`. Stopping a run is `artifactr:stop_run`; recording a fact `artifactr:record`; holding a thread `artifactr:claim_thread`; and a consumer's place in the log `artifactr:save_cursor` and `artifactr:read_cursors`.
- **`Workspaces` holds the hooks:** `Workspaces(storage, ..., authorize=, on_open=)`. `Workspaces.open`, `artifactr_router` and `ArtifactrMcp` no longer take `authorize`, so no surface can be given a different hook, or none.
- **Every public `Workspace` method asks first,** as the handle's actor, through `Workspace.check(access)`, which raises `Forbidden` (`"artifactr:edit_artifact is refused in this workspace"`). A handle from `as_actor` asks as its own actor. A method that calls another public method (`create`, `post_message` and `artifact`) asks once, through the one it calls. `commit` asks inside its span, so a refusal is counted as a rejection, like any other.
- **`Access` names what the call names,** without loading anything: a command's `thread_id` and `artifact_id`, a proposed change's, a feedback target's, and a read's argument. `respond_to_proposal`, `answer_deferred` and `stop_run`'s run lookup carry no artifact or thread yet; phase 5 of the RFC, which hides threads and artifacts, refines them.
- **`check` is public** for what a surface does beside the workspace: the runner asks `artifactr:stop_run`, with the run's thread, before it stops a run, and the MCP server asks `artifactr:read_artifacts` for each artifact a subscription names, as a read of it is asked.
- **Opening asks `artifactr:open`, then calls `on_open`.** `on_open` is called on every allowed open, and its callees are idempotent, so a permission check has no side effects. The template's mirrors start there.
- **The runner's own work acts as the runner.** A command, and the reads that find what it is about, are checked as its sender. Holding a thread, keeping the runner's cursors and planning turns use a handle acting as `SystemActor(name="runner")`, which already recorded abandoned runs. A sender is never asked for `artifactr:claim_thread` or `artifactr:save_cursor`.
- **A cursor saved with a command or a fact** (`commit(..., cursor=)`, `record(..., cursor=)`) is covered by that command's or fact's check; only `save_cursor` asks `artifactr:save_cursor`.
- **The MCP server follows a workspace's log as itself,** `SystemActor(name="mcp")`, not as the client whose tool call first opened it, so that client's later refusal doesn't stop other clients' notifications.
- **A WebSocket that may not read the log or the runs** is closed with 4403 before `welcome`, as one refused its workspace is.
- **The cores' fixed checks stay beneath the hook.** An evaluator only gives feedback, only a thread's agent or the system records run facts, and an author cannot accept their own proposal. The last now looks through `on_behalf_of` ([ADR-0057](0057-a-turn-acts-for-one-author.md)).
- **No hook allows everything,** so the library stays usable alone, as docplan uses it.
- **A permission-matrix test** (`tests/test_access.py`) lists every public `Workspace` method with its action, and every REST route, WebSocket command, and MCP tool and resource with what its caller is asked for. It calls each with a hook that records what it is asked. A method or surface missing from the tables, an action outside `ACTIONS`, or an action in `ACTIONS` nothing asks for fails it. What asks nothing on purpose (`as_actor`, `check`, listing MCP's tools and resource templates) is listed with its reason.

## Options considered

### Option A: a check inside each method (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one `check` call at the top of each method |
| Coverage | Every surface, in-process calls and the agent's tools alike |
| Cost | One hook call per method call |

**Pros:** a surface cannot forget it; the matrix test proves each method's action by calling it.
**Cons:** a surface that calls several methods asks several times.

### Option B: a decorator naming each method's action

| Dimension | Assessment |
|---|---|
| Complexity | Medium: the decorator must reach each call's ids, and wrap generators and context managers |
| Coverage | As A |

**Pros:** the action sits beside the signature.
**Cons:** `subscribe` is an async generator and `claim_thread` an async context manager, so it needs three shapes, and the ids an `Access` carries come from arguments it would have to know by name.

### Option C: a second `permit` hook beside the old `authorize`

Rejected by the RFC (D1): two hooks, and a surface can forget one.

## Trade-off analysis

A check per method costs a hook call per call; with grantr's SQL adapter that is one indexed query, and a request may reuse its own answers. It buys the RFC's guarantee that nothing reaches storage unasked. The explicit call reads plainly in each method and handles the generator and the context manager without special cases, which a decorator would not.

## Consequences

- Easier: one hook decides every command and read, wherever it comes from.
- Easier: a role such as "viewer" can be refused edits, which grantr will provide.
- Harder: every application's `authorize` takes the `Access`, and is passed to `Workspaces` rather than to the surfaces. This is a breaking change, released as a minor version before 1.0 ([lattice ADR-0006](../../adr/0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)).
- Harder: a subscription, as a WebSocket or an MCP stream, is checked when it opens; a command on it is checked as it arrives, but its events keep flowing after a revocation until it closes.
- Revisit: the thread and artifact a `respond_to_proposal` or `answer_deferred` is about, when phase 5 needs them.

## Action items

1. [x] `Access`, the widened `Authorize`, `OnOpen` and `ACTIONS`, held by `Workspaces`.
2. [x] A check in every `Workspace` method, and in the runner's `stop_run`.
3. [x] The permission-matrix test.
4. [ ] grantr answers the hook (lattice RFC-0001, phases 2 to 4).
