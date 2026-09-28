# Workspaces, commits and the log

A workspace holds a tenant's artifacts, threads and proposals, and one log of everything that happened to them. Every read and write goes through a `Workspace` handle, and every write is a command committed through it. This page covers handles, commands and their outcomes, versions and conflicts, proposals, threads and the log.

## Opening a workspace

`Workspaces` opens handles over one storage. `open` is the only place a tenant id enters: the handle it returns is bound to that tenant, that workspace and one actor, and nothing on it can reach another tenant ([ADR-0011](../adr/0011-workspace-scoped-artifacts-and-tenant-handles.md)).

```python
from artifactr import InMemoryStorage, UserActor, Workspaces

workspaces = Workspaces(InMemoryStorage(), types=[Plan, Brief])

ws = await workspaces.open("acme", "launch", actor=UserActor(id="u_alice", name="Alice"))
```

Workspaces need no creating: opening one that has never been written to gives an empty workspace. Handles are cheap; open one per request or connection, for the actor making it.

An actor is who does something, and every event is attributed to one:

| Actor | Who |
|---|---|
| `UserActor(id, name=None)` | A person, identified by your application's user id |
| `AgentActor(thread_id, run_id=None, name="assistant")` | A thread's built-in agent. Every run of one thread's agent is the same participant. |
| `ExternalAgentActor(client_id, name=None)` | An agent connected over MCP |
| `SystemActor(name="system")` | Your application itself, for automated changes |

`ws.as_actor(actor)` returns a handle on the same workspace acting as someone else. The agent layer uses it to act as the agent; you can use it for system jobs.

## Commands and outcomes

Commands are the only way anything changes ([ADR-0002](../adr/0002-single-write-path.md)). They are frozen Pydantic models in `artifactr.core`, and `ws.commit(command)` runs the rules in one storage transaction and returns the outcome:

| Command | What it does | Outcome |
|---|---|---|
| `CreateArtifact(kind, data, artifact_id?, thread_id?)` | Creates an artifact at version 1 | `Applied` or `Proposed` |
| `EditArtifact(artifact_id, base_version, patch, summary?, thread_id?)` | Applies a patch | `Applied` or `Proposed` |
| `ArchiveArtifact(artifact_id, base_version, thread_id?)` | Archives an artifact; it stays readable | `Applied` or `Proposed` |
| `ProposeChange(change, rationale?)` | Proposes a create, edit or archive for someone else to answer | `Proposed` |
| `RespondToProposal(proposal_id, decision, changes?, reason?)` | Accepts or rejects a proposal | `Resolved` |
| `CreateThread(thread_id?, title="")` | Creates a thread (a chat) | `Recorded` |
| `PostMessage(thread_id, content)` | Posts a message as the handle's actor | `Recorded` |
| `SetFocus(thread_id, artifact_ids)` | Sets the artifacts a thread follows | `Recorded` |
| `SetThreadMode(thread_id, mode)` | Switches a thread between `"edit"` and `"suggest"` | `Recorded` |
| `AnswerDeferred(run_id, tool_call_id, answer?, approved?)` | Answers a paused run's question or approval | `Recorded` |

`Applied(artifact_id, version)` means a change was written; `Proposed(proposal_id)` means the artifact type's write policy turned an agent's change into a proposal; `Resolved(proposal_id, decision, version)` answers a proposal; `Recorded()` covers the rest. Every outcome carries the `seq` of the last event the command appended, or `None` if it appended none (setting a focus the thread already has, for example). `commit` is typed with overloads, so `await ws.commit(RespondToProposal(...))` is known to return `Resolved`.

Commands carry the ids of anything they create. Ids are generated when you omit them, and you can pass your own, such as `CreateThread(thread_id="thr_launch")`. The same command against the same state always gives the same result, which is what lets the rules be pure ([ADR-0018](../adr/0018-core-host-contract.md)).

Most applications build commands through helpers rather than by hand:

```python
from artifactr.core import SetFocus

thread = await ws.create_thread("Launch planning")  # returns the Thread
await ws.create(Plan(goal="Ship v1"), artifact_id="plan_1")  # CreateArtifact from an instance
await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("plan_1",)))
await ws.post_message(thread.id, "Let's plan the launch.")

plan = await ws.get(Plan, "plan_1")  # Versioned[Plan]
await ws.commit(plan.edit(lambda p: p.add_task("Write the changelog")))  # EditArtifact
await ws.commit(plan.archive())  # ArchiveArtifact
```

!!! tip "Messages that should reach the agent"

    `ws.post_message` only records a message. To post a message that starts, steers or answers the thread's agent, send it through the `Runner` with `runner.send(ws, thread_id, content)`; see [The agent](agent.md#running-the-agent).

## Reading

| Method | Returns |
|---|---|
| `get(Plan, artifact_id)` | The current `Versioned[Plan]`, or raises `NotFound` if there is none of that type |
| `artifact(artifact_id)` | The current version, whatever its type |
| `artifacts(Plan, include_archived=False)` | Current artifacts of a type (all types by default), oldest first |
| `revisions(artifact_id)` | Every `Revision` of an artifact, oldest first |
| `thread(thread_id)`, `threads()` | Threads, with their mode and focus |
| `proposal(proposal_id)`, `proposals(status="pending")` | Proposals; `status=None` for all |
| `run(run_id)`, `runs(thread_id=None, status=None)` | Agent runs, with any requests a paused run is waiting on |
| `head_seq()` | The log's latest `seq`, or 0 |

A stored artifact is a `Versioned[T]`: its `id`, `version`, `data` (an instance of your type), `updated_by` (the actor of the latest change) and `archived`. It is frozen; change it by committing a command built from it.

## Versions and conflicts

Every edit names the version it was based on, and it applies only if that is still the current version ([ADR-0004](../adr/0004-optimistic-concurrency-and-revisions.md)). Otherwise it is rejected with `VersionConflict`, carrying `base` (what the edit was based on) and `head` (the current version):

```python
from artifactr import VersionConflict

plan = await ws.get(Plan, "plan_1")
try:
    await ws.commit(plan.edit(lambda p: p.add_task("Book the venue")))
except VersionConflict:
    plan = await ws.get(Plan, "plan_1")  # someone changed it; read it again and retry
    await ws.commit(plan.edit(lambda p: p.add_task("Book the venue")))
```

A UI can instead show the person what changed and let them decide. Agents never handle this themselves: the capability turns a conflict into a retry that tells the model to read the artifact again.

Revisions are append-only. Each records the version, the patch, the resulting data, the actor and the proposal it came from, if any. Versions never go backwards: restoring old content is a new edit.

## Rejections

A command that cannot apply raises a `Rejection` and changes nothing. Each has a stable `code`, sent to clients in `command_result` frames, and `payload()` gives its typed details:

| Rejection | Code | When |
|---|---|---|
| `VersionConflict` | `version_conflict` | The edit was based on an older version (`artifact_id`, `base`, `head`) |
| `ValidationFailed` | `validation_failed` | The result does not validate against the type (`errors`) |
| `PatchFailed` | `patch_failed` | The patch does not apply, such as an anchor that is missing or ambiguous |
| `NotFound` | `not_found` | Something the command names does not exist, or its type is not allowed (`entity`, `id`) |
| `Forbidden` | `forbidden` | The actor may not do this, such as answering its own proposal |
| `InvalidState` | `invalid_state` | The command does not fit the current state, such as editing an archived artifact |

## Proposals

A proposal is a change waiting for a decision. Agents' changes become proposals under a `"propose"` write policy or in a suggest-mode thread, and anyone can propose explicitly:

```python
from artifactr.core import ProposeChange, RespondToProposal

brief = await ws.get(Brief, "brief")
proposed = await ws.commit(
    ProposeChange(change=brief.edit_text("## v1", "## v1.0"), rationale="match the tag names")
)

bob = ws.as_actor(UserActor(id="u_bob", name="Bob"))
await bob.commit(RespondToProposal(proposal_id=proposed.proposal_id, decision="accept"))
```

- The change must apply when it is proposed, so a proposal is never known to be broken.
- A proposal must be answered by someone other than its author; answering your own raises `Forbidden`.
- Accepting applies the change to the artifact's **current** version, not the one it was proposed against, so proposals survive other edits made meanwhile. `changes` is an optional patch layered on top, so a person can accept with their own edits.
- Rejecting takes an optional `reason`, which the proposer is told.
- The new revision is attributed to whoever accepted; the `proposal_resolved` event records who proposed it.

Proposals do not block anyone ([ADR-0009](../adr/0009-write-policies-and-non-blocking-proposals.md)). The agent keeps working after proposing, and hears the decision as a change note whenever it comes.

## Threads

A thread is a chat. It has a title, a mode and a focus:

- **Focus** is the list of artifacts the thread follows. The agent sees followed artifacts in its instructions and hears about other participants' changes to them. The agent's generic tools add artifacts to the focus as it reads, creates or edits them; set it yourself with `SetFocus`.
- **Mode** is `"edit"` (the default) or `"suggest"`. In suggest mode, the thread's agent proposes every change.

Artifacts belong to the workspace, not to a thread, so several threads and people can work on the same artifact.

## The log

Every command and every fact about an agent run appends events to the workspace's log, in one transaction with the change itself ([ADR-0005](../adr/0005-one-event-log-per-workspace.md)). Each event travels in an `Envelope`:

| Field | Meaning |
|---|---|
| `seq` | Its position in the workspace's log: gap-free, from 1 |
| `id`, `ts` | A unique id and the time it was stored |
| `workspace_id`, `thread_id`, `run_id` | Where it belongs; `thread_id` and `run_id` are set when there is one |
| `actor` | Who did it |
| `event` | The event itself, one of the types in `artifactr.core` |

`read(after_seq=0, threads=None, limit=None)` returns a page of the log. `subscribe(after_seq=0, threads=None)` yields the stored envelopes after `after_seq` and then each new one as it commits, on one iterator, so nothing falls between catching up and following along:

```python
async for envelope in ws.subscribe(after_seq=last_seen_seq, threads={thread.id}):
    handle(envelope)
```

`threads` filters thread-scoped events (messages, runs, focus and mode) to the listed threads. Workspace-scoped events (artifacts and proposals) are always delivered, whichever thread they came from.

Core events form a closed set, so code that handles them can `match` exhaustively and pyright checks it. Applications record their own facts as `AppEvent`s, which any actor can record:

```python
from artifactr.core import AppEvent

await ws.record(AppEvent(name="exported", data={"format": "pdf"}, thread_id=thread.id))
```

## Change notes

`change_notes` turns a slice of the log into short, attributed notes for one viewer. It is what the agent is told, and a UI can show the same thing to people:

```python
from artifactr.core import render_notes

notes = await ws.change_notes(after_seq=last_seen_seq, focus={"plan_1"})
print(render_notes(notes))
```

```text
- Alice changed plan_1 (plan, v7 → v9): completed Ship v1; moved the goal
- Bob proposed a change to plan_1 (prp_d094e124644e0444): match the tag names
```

Notes leave out the viewer's own actions, cover only the artifacts in `focus` (all of them when it is `None`), and combine several changes to one artifact into one note. The viewer defaults to the handle's actor.
