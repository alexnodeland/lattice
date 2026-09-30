# Getting started

This page builds a small application: a launch plan that a person and an agent work on together. The agent may only propose changes to the plan, and the person accepts them. Along the way it covers the pieces every artifactr application has: an artifact type, a workspace, an agent with the `ArtifactWorkspace` capability, a `Runner`, and a web surface.

## Install

artifactr needs Python 3.12 or newer. It is distributed as `artifactr-ai` and imported as `artifactr`. Until it is published to PyPI, install it from its directory in [lattice](https://github.com/alexnodeland/lattice), the family's repository:

=== "uv"

    ```bash
    uv add "artifactr-ai @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"
    ```

=== "pip"

    ```bash
    pip install "artifactr-ai @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"
    ```

!!! warning "`artifactr-ai`, not `artifactr`"

    The name `artifactr` on PyPI belongs to an unrelated project, so this library is distributed as `artifactr-ai`. Its import name is still `artifactr`.

The core install covers artifact types, workspaces with in-memory storage, and the pydantic-ai integration. The adapters are optional extras:

| Extra | Adds | Install |
|---|---|---|
| `fastapi` | The WebSocket thread protocol and REST endpoints, as a FastAPI router | `"artifactr-ai[fastapi] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `mcp` | An MCP server for external agents | `"artifactr-ai[mcp] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `postgres` | [SQL storage](guides/storage.md#sql-storage) on PostgreSQL, with asyncpg | `"artifactr-ai[postgres] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `sqlite` | SQL storage on SQLite, with aiosqlite | `"artifactr-ai[sqlite] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `sql` | SQL storage without a driver, if you bring your own | `"artifactr-ai[sql] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `langfuse` | [Langfuse](guides/observability.md#langfuse): whole traces, each turn's session and user, and feedback as scores | `"artifactr-ai[langfuse] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `litellm` | [The LLM gateway](guides/gateway.md): models over a LiteLLM proxy, with tenancy, keys and guardrails per request | `"artifactr-ai[litellm] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |
| `otel` | [`configure_telemetry`](guides/observability.md): the OpenTelemetry SDK, OTLP export and instrumentation in one call | `"artifactr-ai[otel] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"` |

Combine extras with commas, as in `artifactr-ai[fastapi,postgres]`. You also need the pydantic-ai extra for your model provider, such as `pydantic-ai-slim[anthropic]` or `pydantic-ai-slim[openai]`, and its API key in the environment.

!!! note "evalr comes from lattice too"

    The `langfuse` extra, and the `evals` extra ([Evaluation](guides/evaluation.md#evaluating-with-evalr)), depend on [evalr](../evalr/index.md), which is not on PyPI yet either. uv installs it from the same commit of lattice as artifactr. pip reads only the version ranges, so with pip, install evalr from lattice as well: `pip install "evalr @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/evalr" "artifactr-ai[langfuse] @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/artifactr"`.

## 1. Define an artifact type

An artifact type is a Pydantic model that subclasses `Artifact`. Defining the class registers it under a name derived from the class name, here `plan`.

```python
from typing import ClassVar

from pydantic import BaseModel

from artifactr import Artifact, WritePolicy, new_id


class Task(BaseModel):
    title: str
    done: bool = False


class Plan(Artifact):  # registered as "plan"
    write_policy: ClassVar[WritePolicy] = "propose"  # agents propose, people decide

    goal: str = ""
    tasks: dict[str, Task] = {}  # keyed by id, so patch paths stay stable

    def add_task(self, title: str) -> None:
        self.tasks[new_id("task")] = Task(title=title)

    def render_for_agent(self) -> str:
        lines = [f"Goal: {self.goal}"]
        lines += [f"- [{'x' if t.done else ' '}] {t.title}" for t in self.tasks.values()]
        return "\n".join(lines)
```

`write_policy = "propose"` means an agent's change to a plan is recorded as a proposal for someone to accept. People's changes apply directly. `render_for_agent` controls what the agent sees; without it, the agent sees the data as JSON. [Defining artifact types](guides/artifact-types.md) covers the rest, including Markdown documents.

## 2. Give an agent the capability

The agent is an ordinary pydantic-ai `Agent`. Its dependencies are a `Session`, and the `ArtifactWorkspace` capability makes it a participant in the workspace: it adds the generic artifact tools (list, read, create, edit text, archive), renders the artifacts the thread follows into its instructions, tells it what others changed, and records everything it does.

Structured edits belong in the application's own tools. This one adds a task to a plan:

```python
from pydantic_ai import Agent, FunctionToolset, RunContext

from artifactr import ArtifactWorkspace, Session
from artifactr.agent import describe_outcome

plan_tools = FunctionToolset[Session[None]]()


@plan_tools.tool
async def add_task(ctx: RunContext[Session[None]], plan_id: str, title: str) -> str:
    """Add a task to a plan."""
    plan = await ctx.deps.workspace.get(Plan, plan_id)
    outcome = await ctx.deps.workspace.commit(plan.edit(lambda p: p.add_task(title)))
    return describe_outcome(outcome)


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[None],
    toolsets=[plan_tools],
    capabilities=[ArtifactWorkspace(types=[Plan])],
)
```

`ctx.deps.workspace` acts as the agent, so the commit is attributed to it. `plan.edit(...)` copies the plan, applies your change to the copy, and turns the difference into a patch against the version you read. Because plans use the `propose` policy, the commit returns `Proposed` rather than `Applied`, and `describe_outcome` tells the model so. `Session[None]` says the application passes no dependencies of its own; pass your database, clients or settings there instead.

## 3. Open a workspace and run the agent

A `Workspaces` object opens tenant-scoped workspace handles over a storage. Each handle acts as one actor, and every write goes through it. A `Runner` runs the agent in the workspace's threads.

```python
from artifactr import InMemoryStorage, Runner, UserActor, Workspaces
from artifactr.core import RespondToProposal, SetFocus

runner = Runner(agent, app=None)
workspaces = Workspaces(InMemoryStorage(), types=[Plan])


async def main() -> None:
    alice = UserActor(id="u_alice", name="Alice")
    ws = await workspaces.open("acme", "launch", actor=alice)

    thread = await ws.create_thread("Launch planning")
    await ws.create(Plan(goal="Ship v1"), artifact_id="plan_1")
    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("plan_1",)))

    sent = await runner.send(ws, thread.id, "Break the launch into tasks.")
    if sent.run is not None:
        await sent.run.wait()

    for proposal in await ws.proposals():
        await ws.commit(RespondToProposal(proposal_id=proposal.id, decision="accept"))
```

- `Workspaces(..., types=[Plan])` is an allowlist: clients cannot create artifact types you did not list.
- `SetFocus` makes the thread follow the plan. The agent sees followed artifacts in its instructions, and is told when someone else changes them.
- `runner.send` posts Alice's message and starts a run, because the thread is idle. In a busy thread the same call steers the running agent instead. It returns a `Sent` whose `run` is the run it started, if any.
- Alice accepts each proposal the agent made. Accepting applies the change on top of the plan's current version.

`InMemoryStorage` keeps everything in the process, which suits tests and prototypes. See [Storage](guides/storage.md) for durable storage.

## 4. Read what happened

Every step above is on the workspace's log, in order, with its actor. At the end of `main`:

```python
for envelope in await ws.read():
    print(envelope.seq, envelope.actor.kind, envelope.event.type)
```

```text
1 user thread_created
2 user artifact_created
3 user focus_changed
4 user message_posted
5 agent run_started
6 agent tool_called
7 agent proposal_created
8 agent tool_returned
9 agent tool_called
10 agent proposal_created
11 agent tool_returned
12 agent message_posted
13 agent run_ended
14 user artifact_changed
15 user proposal_resolved
16 user artifact_changed
17 user proposal_resolved
```

The exact tool calls depend on the model; this run added two tasks. The agent's reply is on the log too (`message_posted`), and so is its model history, so the next message in the thread continues the same conversation.

??? example "The complete script"

    ```python title="app.py"
    import asyncio
    from typing import ClassVar

    from pydantic import BaseModel
    from pydantic_ai import Agent, FunctionToolset, RunContext

    from artifactr import (
        Artifact,
        ArtifactWorkspace,
        InMemoryStorage,
        Runner,
        Session,
        UserActor,
        Workspaces,
        WritePolicy,
        new_id,
    )
    from artifactr.agent import describe_outcome
    from artifactr.core import RespondToProposal, SetFocus


    class Task(BaseModel):
        title: str
        done: bool = False


    class Plan(Artifact):  # registered as "plan"
        write_policy: ClassVar[WritePolicy] = "propose"  # agents propose, people decide

        goal: str = ""
        tasks: dict[str, Task] = {}  # keyed by id, so patch paths stay stable

        def add_task(self, title: str) -> None:
            self.tasks[new_id("task")] = Task(title=title)

        def render_for_agent(self) -> str:
            lines = [f"Goal: {self.goal}"]
            lines += [f"- [{'x' if t.done else ' '}] {t.title}" for t in self.tasks.values()]
            return "\n".join(lines)


    plan_tools = FunctionToolset[Session[None]]()


    @plan_tools.tool
    async def add_task(ctx: RunContext[Session[None]], plan_id: str, title: str) -> str:
        """Add a task to a plan."""
        plan = await ctx.deps.workspace.get(Plan, plan_id)
        outcome = await ctx.deps.workspace.commit(plan.edit(lambda p: p.add_task(title)))
        return describe_outcome(outcome)


    agent = Agent(
        "anthropic:claude-sonnet-5-5",
        deps_type=Session[None],
        toolsets=[plan_tools],
        capabilities=[ArtifactWorkspace(types=[Plan])],
    )
    runner = Runner(agent, app=None)
    workspaces = Workspaces(InMemoryStorage(), types=[Plan])


    async def main() -> None:
        alice = UserActor(id="u_alice", name="Alice")
        ws = await workspaces.open("acme", "launch", actor=alice)

        thread = await ws.create_thread("Launch planning")
        await ws.create(Plan(goal="Ship v1"), artifact_id="plan_1")
        await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("plan_1",)))

        sent = await runner.send(ws, thread.id, "Break the launch into tasks.")
        if sent.run is not None:
            await sent.run.wait()

        for proposal in await ws.proposals():
            await ws.commit(RespondToProposal(proposal_id=proposal.id, decision="accept"))

        for envelope in await ws.read():
            print(envelope.seq, envelope.actor.kind, envelope.event.type)


    asyncio.run(main())
    ```

## 5. Serve it

A chat frontend needs to send messages and see changes as they happen. Install the `fastapi` extra and include the router, giving it your authentication:

```python
from fastapi import FastAPI
from starlette.requests import HTTPConnection

from artifactr import UserActor
from artifactr.core import Actor, TenantId
from artifactr.fastapi import Unauthorized, artifactr_router


async def resolve_actor(connection: HTTPConnection) -> tuple[TenantId, Actor]:
    user = await authenticate(connection)  # your application's authentication
    if user is None:
        raise Unauthorized("sign in first")
    return user.tenant_id, UserActor(id=user.id, name=user.name)


app = FastAPI()
app.include_router(artifactr_router(workspaces, runner, resolve_actor=resolve_actor), prefix="/v1")
```

Clients connect a WebSocket to `/v1/workspaces/{workspace_id}/stream`, say `hello` with the last `seq` they saw, and receive the log from there followed by live events, command results and the agent's streamed output. The same commands are available as `POST /v1/workspaces/{workspace_id}/commands`. [Serving over WebSocket and REST](guides/serving.md) covers the endpoints and authentication, and the [thread protocol](protocol.md) specifies every frame.

## Next steps

- Read the [guides](guides/artifact-types.md), starting with [defining artifact types](guides/artifact-types.md) and [workspaces](guides/workspaces.md).
- Let external agents such as coding assistants join a workspace over [MCP](guides/mcp.md).
- See how to [test](guides/testing.md) an application without calling a model.
- Run the [reference implementation](reference-implementation.md), `examples/docplan`: a Markdown document and a structured plan, their tools, a server with every surface, and a terminal client.
