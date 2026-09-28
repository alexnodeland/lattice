---
title: artifactr
description: A Python library for chat applications where people and agents collaborate through shared, versioned artifacts.
hide:
  - navigation
---

<div class="artifactr-hero" markdown>

<h1 class="artifactr-visually-hidden">artifactr</h1>

![artifactr](assets/brand/lockup-light.svg#gh-light-mode-only)
![artifactr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

A Python library for chat applications in which people and agents work on the same documents, plans and specs, with every change versioned, attributed and fed back into the agent's context.

</div>

!!! note "Pre-release"

    artifactr is at version 0.1.0.dev0 and has not been released. Everything described here is built ([RFC-0001](rfcs/0001-v0.1-implementation-plan.md)), and the API may still change before the first release.

## Why: the second channel

In most chat applications the conversation is the only channel. When an agent drafts a plan, the plan lives inside a message; when a person wants to change it, they describe the change in another message and hope the agent applies it.

artifactr adds a second channel. The artifacts (a Markdown brief, a task plan, a spec, anything with structure) live beside the chat, and both sides edit them directly. Those edits carry information the conversation does not: when a person rewrites a paragraph the agent drafted, or the agent restructures a plan, the change itself says something about how each side is thinking. So artifactr treats every edit as a first-class event:

- **Versioned.** Every change writes a new revision. A stale edit is rejected, not silently merged.
- **Attributed.** Every event names its actor: a person, the thread's agent, an external agent, or the system.
- **Visible.** Every participant sees every change, on one ordered log per workspace.
- **Fed back.** The agent is told what others changed since it last looked, in their words, before it acts.

## A short example

A person edits a brief, then asks the agent for more. The agent is told about the edit before it starts, and its own edit is recorded the same way.

```python
import asyncio

from pydantic_ai import Agent

from artifactr import (
    ArtifactWorkspace,
    InMemoryStorage,
    MarkdownArtifact,
    Runner,
    Session,
    UserActor,
    Workspaces,
)
from artifactr.core import SetFocus


class Brief(MarkdownArtifact):  # an artifact type: a Pydantic model, registered as "brief"
    pass


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[None],
    capabilities=[ArtifactWorkspace(types=[Brief])],  # tools, instructions and change notes
)
runner = Runner(agent, app=None)
workspaces = Workspaces(InMemoryStorage(), types=[Brief])


async def main() -> None:
    alice = UserActor(id="u_alice", name="Alice")
    ws = await workspaces.open("acme", "launch", actor=alice)
    thread = await ws.create_thread("Launch brief")

    await ws.create(Brief(text="# Launch\n\nWe ship on Friday."), artifact_id="brief")
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("brief",)))

    brief = await ws.get(Brief, "brief")
    await ws.commit(brief.edit_text("Friday", "Monday"))  # version 2, by Alice

    sent = await runner.send(ws, thread.id, "Add a risks section to the brief.")
    if sent.run is not None:
        await sent.run.wait()  # the agent is told what Alice changed before it starts

    for envelope in await ws.read():
        print(envelope.seq, envelope.actor.kind, envelope.event.type)


asyncio.run(main())
```

The workspace's log tells the whole story, in order:

```text
1 user thread_created
2 user artifact_created
3 user focus_changed
4 user artifact_changed
5 user message_posted
6 agent run_started
7 agent tool_called
8 agent artifact_changed
9 agent tool_returned
10 agent message_posted
11 agent run_ended
```

[Getting started](getting-started.md) builds a fuller application step by step, with a structured plan, an application tool and proposals.

## What you get

- **Artifact types as Pydantic models.** Subclass `Artifact`, add fields, and the library provides versioning, validation, patches, change summaries and agent tools. [Defining artifact types](guides/artifact-types.md)
- **One write path.** Every change, from any participant and any surface, is a command committed through a workspace handle, checked against the artifact's version and appended to the workspace's log. [Workspaces, commits and the log](guides/workspaces.md)
- **Proposals without blocking.** An artifact type can require agents to propose changes. The agent keeps working; a person accepts, edits or rejects the proposal whenever they like, and the agent hears the outcome. [The agent](guides/agent.md#proposals)
- **An agent that follows along.** One pydantic-ai capability gives an agent the generic artifact tools, instructions rendered fresh for every request, notes on what others changed, steering by messages sent mid-run, and pauses for questions and approvals. [The agent](guides/agent.md)
- **Live output kept apart from history.** Token-level output streams to whoever is watching a run; the log holds only durable facts. [Live output](guides/live-output.md)
- **Surfaces that behave the same.** A WebSocket thread protocol and REST endpoints for your frontend, and an MCP server for external agents, all carrying commands to the same handler. [Serving over WebSocket and REST](guides/serving.md), [External agents over MCP](guides/mcp.md)
- **Tenant isolation by construction.** A workspace handle is bound to one tenant and one actor; nothing below it accepts a tenant id. [Multi-tenancy and security](guides/security.md)
- **Rules you can read and port.** The rules live in a pure, synchronous core, pinned by language-neutral conformance fixtures, and the library is held to 100% branch coverage and pyright strict. [Architecture](architecture.md)

## Where to go next

| If you want to | Read |
|---|---|
| Build something now | [Getting started](getting-started.md) |
| Understand one part in depth | The [guides](guides/artifact-types.md) |
| Look up a class or function | The [API reference](reference/index.md) |
| Write a frontend | The [thread protocol](protocol.md) and its [JSON Schema](reference/schema.md) |
| Understand why it is built this way | The [architecture](architecture.md) and the [decision records](adr/README.md) |
| Contribute | [Contributing](project/contributing.md) |
