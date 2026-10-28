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
| `TextDelta` | `part`, `delta`, `offset` | More text; `offset` is where it starts in the part |
| `ThinkingDelta` | `part`, `delta`, `offset` | More thinking, with its offset |
| `ToolArgsDelta` | `part`, `delta` | More of a tool call's JSON arguments |
| `PartEnded` | `part` | The part is complete |
| `Draft` | `kind`, `data`, `artifact_id` | An application tool's `ArtifactDraft` |
| `AppLive` | `name`, `data` | Any other pydantic-ai `CustomEvent` a tool emits |

`part` is the index of the response part, so a client can keep several parts apart. The [thread protocol](../protocol.md#live-ephemeral) gives the wire format.

A model that streams a token at a time would send a frame a token. `forward_live` gathers a part's text and thinking deltas for 50 milliseconds (`forward_live(channel, coalesce=...)`; `0` sends each as it comes) and sends them as one delta, so a watcher sees the reply grow a few words at a time at most twenty times a second; any other event, such as the part's end, sends what is gathered first, so frames keep the stream's order. Each delta carries `offset`, where it starts in its part in UTF-16 code units, as JavaScript counts a string, counting from 0 at each `part_started`; a response's parts are numbered from 0 again, so a part is known by its response and index. A watcher that attaches mid-run is sent the run's buffered frames first, so it may be sent a delta it already has: writing each delta at its offset, rather than appending it, makes the second sending harmless, and a delta past the end of what it has, or without an offset, is appended ([the protocol](../protocol.md#live-ephemeral) spells the rule out).

## A model that sends nothing

A request that never answers, or a stream that stops mid-reply, would otherwise hold its thread for as long as the client library waits, ten minutes through a gateway, with no sign of progress. The runner times each turn's stream (`Runner(liveness=Liveness(...))`): a model request must send its first event within `first_output` seconds and each later one within `no_output` (two minutes each by default), and a tool call must return within `tool` (ten minutes; `None` waits as long as the tool needs; a deployment whose workers legitimately take longer raises it, stackr's template from `AGENT_TOOL_SECONDS`). A wait that runs out tears the request down and fails the run with the reason `model_stalled`, or `tool_stalled`, naming the model, or the calls still running, and the wait; its usage so far is recorded, and the thread is released for the next message. A run stopped while its model stalls is stopped, as any stop is. The model is classed by the name the run context gives, the gateway's alias through LiteLLM, which does the falling back between providers; pydantic-ai's `FallbackModel` is not used. A model served locally is slower to its first token, so `local_first_output` and `local_no_output` (five minutes each) apply to one; `is_local_model(name)` tells them apart by name, LiteLLM's local providers' prefixes (`ollama/`, `lm_studio/`, `omlx/`, `llamacpp/`, `vllm/`) and the `local` aliases, with `Liveness(local_models=..., hosted_models=...)` as the application's last word, and an unknown name counts as hosted ([ADR-0095](../adr/0095-a-run-that-waits-on-nothing-is-failed-and-a-message-that-starts-nothing-is-told.md)).

## Token counts

As each model request ends, `ArtifactWorkspace` sends a `usage` frame: what the request used, as the provider counted it (input, output, of the input what was read from and written to the prompt cache, of the output what was spent reasoning), the model that answered, as the response names it, how long the request took, and the run's total so far. The total is a whole count, not an increment, so a client replaces what it has with the total that counts the most requests, and a frame it is sent again on reconnect counts nothing twice. Every `run_ended` and `run_paused` carries the same in `usage`, each request a step of `usage.steps`, whether the run completed, paused, was stopped or failed. Until the first request ends, a client can only estimate ([ADR-0096](../adr/0096-a-run-counts-each-model-request-exactly-live-and-at-its-end.md)).

The model a step names is the one that answered, which can differ from the one the run asked for, `run_started.model`, when a gateway falls back to another: a client that shows the model shows the step's, so a fallback is never silent ([ADR-0097](../adr/0097-a-message-chooses-the-model-of-the-turn-it-starts.md)).

Through an OpenAI-compatible gateway, pydantic-ai maps `prompt_tokens_details.cached_tokens` to the cache read and `completion_tokens_details.reasoning_tokens` to the reasoning; LiteLLM reports Anthropic's cache writes as a top-level `cache_creation_input_tokens`, which artifactr reads too. A provider that says none of these counts 0.

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
