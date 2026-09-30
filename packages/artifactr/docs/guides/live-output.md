# Live output

A run produces two kinds of output. **Durable events** (the agent's message, the artifacts it changed, the tools it called) go on the workspace's log, where every participant sees them and a reconnecting client replays them. **Live output** (the reply as it streams token by token, thinking, tool arguments as they are generated, drafts of artifacts in progress) is ephemeral: it is sent to whoever is watching the run and never stored ([ADR-0007](../adr/0007-caller-owned-live-output.md)).

Keeping them apart keeps the log small and meaningful, and losing live output is harmless: when the agent's `message_posted` event arrives, it is the authoritative text of the reply, and `artifact_changed` replaces any draft of that artifact.

## Watching a run

The `Runner` sends every run's live output to its `live` channel, a `FanoutChannel` by default. `runner.watch(run_id)` yields the run's frames: first what the run has produced so far, then each new frame until the run ends.

```python
sent = await runner.send(ws, thread.id, "Draft the launch brief.")
if sent.run is not None:
    async for frame in runner.watch(sent.run.run_id):
        match frame.event:
            case TextDelta(delta=delta):
                print(delta, end="", flush=True)
            case Draft(kind=kind, data=data):
                show_draft(kind, data)
            case _:
                pass
```

`TextDelta` and `Draft` are in `artifactr.core`. The WebSocket surface does this for you: a client receives live frames for runs in the threads it follows, and can attach to any run with a `watch_run` command.

Delivery is best-effort. Each run keeps its most recent frames (1,024 by default), and a watcher that falls behind loses its oldest frames rather than slowing the run. Within one run, frames arrive in order. Watching a run that has ended returns at once.

## Live events

Each frame is a `LiveFrame` with the `run_id` and one event:

| Event | Fields | From |
|---|---|---|
| `PartStarted` | `part`, `part_kind` (`text`, `thinking` or `tool_call`), `tool_name` | The model starting a response part |
| `TextDelta` | `part`, `delta` | More text |
| `ThinkingDelta` | `part`, `delta` | More thinking |
| `ToolArgsDelta` | `part`, `delta` | More of a tool call's JSON arguments |
| `PartEnded` | `part` | The part is complete |
| `Draft` | `kind`, `data`, `artifact_id` | An application tool's `ArtifactDraft` |
| `AppLive` | `name`, `data` | Any other pydantic-ai `CustomEvent` a tool emits |

`part` is the index of the response part, so a client can keep several parts apart. The [thread protocol](../protocol.md#live-ephemeral) gives the wire format.

## Drafts and progress from your tools

A tool that generates an artifact over several steps can show its progress before committing anything. Emit an `ArtifactDraft`, a full snapshot of the artifact so far:

```python
from artifactr import ArtifactDraft


@plan_tools.tool
async def draft_plan(ctx: RunContext[Session[AppDeps]], goal: str) -> str:
    """Draft a plan for a goal, step by step."""
    plan = Plan(goal=goal)
    for title in await ctx.deps.app.planner.steps(goal):
        plan.add_task(title)
        await ctx.emit(ArtifactDraft(kind="plan", snapshot=plan.to_json()))
    outcome = await ctx.deps.workspace.create(plan)
    return describe_outcome(outcome)
```

The draft's field is `snapshot`, because pydantic-ai's `CustomEvent` reserves `data`. Pass `artifact_id` when drafting a change to an existing artifact. Any other `CustomEvent` subclass a tool emits reaches watchers as an `AppLive` event, named after the event, with its own fields as `data`.

## Driving runs yourself

`forward_live(channel)` returns a pydantic-ai `event_stream_handler` that turns a run's stream into live frames and sends them to a channel. The runner uses it for every run; use it directly when you call `agent.run` yourself:

```python
from artifactr.agent import FanoutChannel, forward_live, load_history

channel = FanoutChannel()
session = Session.start(ws, thread.id, app=deps)
await agent.run(
    prompt,
    deps=session,
    message_history=await load_history(ws, thread.id),
    event_stream_handler=forward_live(channel),
)
channel.close(session.run_id)  # ends every watcher of the run
```

A channel is anything with an async `send(frame)` method (the `LiveChannel` protocol):

| Channel | Use |
|---|---|
| `FanoutChannel(buffer=1024, remember_closed=10_000)` | In-process fan-out keyed by run, with `watch(run_id)` and `close(run_id)`. The runner's default. |
| `NullChannel()` | Drops every frame, for headless runs such as scheduled jobs |

`to_live(event)` translates a single pydantic-ai stream event, if you need the translation without a channel.

A run is held by its thread claim, not by a connection: if the client that started a run disconnects, the run continues, and any connection can watch it. Runs and their live channels live in the process that started them. Fanning out live output across several server processes needs a shared channel, such as Redis or NATS pub/sub, which is an [open question](../architecture.md#open-questions) for after v0.1.
