# The agent

artifactr plugs into [pydantic-ai](https://ai.pydantic.dev) as one capability, `ArtifactWorkspace` ([ADR-0006](../adr/0006-agent-integration-as-pydantic-ai-capability.md)). An agent with it is a participant in a workspace: it reads and edits artifacts through tools, sees the artifacts it follows in its instructions, is told what others changed, and has everything it does recorded on the log. A `Runner` runs such an agent in threads, so a message behaves the same from every surface ([ADR-0020](../adr/0020-running-agents-in-threads.md)).

## Setting up the agent

```python
from dataclasses import dataclass

from pydantic_ai import Agent

from artifactr import ArtifactWorkspace, Runner, Session


@dataclass
class AppDeps:
    search: SearchClient  # whatever your tools need


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[AppDeps],
    toolsets=[plan_tools],  # your own tools
    capabilities=[ArtifactWorkspace(types=[Plan, Brief])],
)
runner = Runner(agent, app=AppDeps(search=SearchClient()))
```

- **`deps_type=Session[AppDeps]`.** The run's dependencies are a `Session`: `workspace` (a handle acting as this thread's agent), `thread_id`, `run_id`, and `app`, your own dependencies. Use `Session[None]` if you have none.
- **`ArtifactWorkspace(types=...)`** lists the artifact types the agent may create. `ask=True` adds the `ask_user` tool (see [Pausing](#pausing-for-people)); `max_render_chars` (4,000) limits how much of each followed artifact goes into the instructions; `max_summary_chars` (200) limits how much of each tool call's arguments and result is recorded; `notices=True` tells the agent about notices (see [Notices](#notices)).
- **`Runner(agent, app=...)`** passes `app` to every run as `ctx.deps.app`. Its other options are `agent_name` (how the agent is named in the workspace, `"assistant"` by default), `claim_ttl` (how long a thread claim survives a dead process, 30 seconds), `live` (where live output goes; see [Live output](live-output.md)) and `results` (where commands' results are remembered, so a retried command is carried out once; see [Serving](serving.md#rest)).

The capability composes with any other capabilities, toolsets, output types and model settings the agent has. A turn is an ordinary pydantic-ai run.

## The generic tools

Every agent with the capability gets tools that work for any artifact type. Their definitions never change between requests, so the provider's prompt cache stays warm.

| Tool | What it does |
|---|---|
| `list_artifacts(kind=None)` | Lists the workspace's artifacts, with their kinds and versions |
| `read_artifact(artifact_id)` | Returns an artifact's current `render_for_agent()` text, and follows it |
| `create_artifact(kind, data)` | Creates an artifact of one of the capability's types; the description includes each type's JSON Schema |
| `edit_text(artifact_id, old, new, field="text", summary=None, propose=False, rationale=None)` | Replaces one exact passage of a text field, or proposes the replacement |
| `archive_artifact(artifact_id)` | Archives an artifact |
| `ask_user(question, choices=None)` | Asks the people in the thread and pauses the run; only with `ask=True` |

Reading, creating or editing an artifact through these tools adds it to the thread's focus, so the agent hears about later changes to it.

## Application tools

Structured edits belong in your own tools: `add_task`, `set_status`, `move_section`. They are plain pydantic-ai tools over `RunContext[Session[AppDeps]]`, registered on the agent, not on the capability ([ADR-0017](../adr/0017-application-toolsets-and-capability-events.md)):

```python
from pydantic_ai import FunctionToolset, RunContext

from artifactr import Applied, Proposed, Session

plan_tools = FunctionToolset[Session[AppDeps]]()


@plan_tools.tool
async def add_task(ctx: RunContext[Session[AppDeps]], plan_id: str, title: str) -> str:
    """Add a task to a plan."""
    plan = await ctx.deps.workspace.get(Plan, plan_id)
    match await ctx.deps.workspace.commit(plan.edit(lambda p: p.add_task(title))):
        case Applied(version=version):
            return f"Added. The plan is now at version {version}."
        case Proposed(proposal_id=proposal_id):
            return f"Proposed adding the task ({proposal_id}); the user will review it."
```

- **Commit through `ctx.deps.workspace`.** It acts as the agent (an `AgentActor` for this thread and run), so every change is attributed to it, and write policies apply.
- **Do not catch rejections.** The capability turns any `Rejection` a tool raises into a retry carrying the rejection's message, and for a `VersionConflict` adds "Read the artifact again, then retry." A tool may also raise pydantic-ai's `ModelRetry` itself, to ask the model to try again with better arguments. Other exceptions are recorded and fail the run.
- **Annotate the context literally** as `RunContext[...]`. pydantic-ai recognizes a tool that takes its context by that annotation, so a type alias would hide it.
- `artifactr.agent.describe_outcome(outcome)` gives the model a standard sentence for any outcome, and `artifactr.agent.submit(workspace, change, propose=..., rationale=...)` commits a change or proposes it, as the generic tools do.

Every tool call, yours included, is recorded as `tool_called` and `tool_returned` events, with clipped summaries of the arguments and result.

## What the agent sees

The capability's instructions are rendered fresh from storage for every model request, so they are never stale, even within one run. They contain:

- a short introduction to working with shared artifacts
- a note that the thread is in suggest mode, when it is
- the kinds of artifact the agent can create
- every artifact the thread follows, as its `render_for_agent()` text inside an `<artifact id="..." kind="..." version="...">` element
- the agent's own proposals awaiting review

## Change notes and steering

The agent is told what other participants did, as short notes in their own words ([ADR-0008](../adr/0008-agent-perception-and-steering.md)):

```text
<workspace-changes>
- Alice changed plan_1 (plan, v7 → v8): completed Ship v1
- Alice rejected your proposal prp_3f9c2a1b7d4e5f60 for plan_1: not before the beta
</workspace-changes>
```

- **When a run starts**, the agent receives the notes it missed since the thread's history was last saved. Nothing is reported twice and nothing is skipped.
- **While a run is in progress**, a watcher follows the log. Others' changes to followed artifacts arrive as notes, and a new message in the thread arrives as-is. Both reach the model at its next request, so a person can steer a long run without stopping it.

Notes cover the artifacts the thread follows, plus artifacts created in the thread. They leave out the agent's own changes, including those of its earlier runs: every run of one thread's agent is the same participant. They arrive as user-prompt parts, so they are stored in the model history with the rest of the conversation.

## Notices

A notice is a message for the people in a thread rather than its agent, such as a rule saying it has gone live: a `PostMessage` of kind `notice` ([ADR-0051](../adr/0051-notices.md)). Whoever may post a message may post a notice.

```python
from artifactr.core import ExternalAgentActor

rule = ws.as_actor(ExternalAgentActor(client_id="reflexr:timeline-entry", name="timeline-entry"))
await rule.post_message(thread.id, "The rule is live.", kind="notice")
```

- **It starts no run, steers none and answers no paused run,** from every surface: `Runner.execute` commits it as it is, and `runner.send` posts messages only.
- **Clients can show it apart:** its `message_posted` has `kind: "notice"`.
- **Its `message_id` is used once,** as a message's is.
- **The agent is not told,** so a notice stays out of the model history, unless the application asks with `ArtifactWorkspace(types=..., notices=True)`. The agent is then told of the notices others post in its thread as notes, when a run starts and while it runs:

```text
<workspace-changes>
- timeline-entry posted a notice: The rule is live.
</workspace-changes>
```

## Running the agent

`runner.send(workspace, thread_id, content)` posts a message as the handle's actor and acts on it. A message means one thing wherever it comes from:

| The thread is | The message |
|---|---|
| Idle | starts a run |
| Running | steers the running agent, which is told at its next request |
| Ending, or pausing: its run no longer takes messages but still holds the thread | is taken by the next turn, which the run starts as it releases the thread |
| Paused on questions or approvals | is the reply: it answers the questions, declines the approvals with the message as the reason, and resumes the run |

Behind the table is one rule: the log decides ([ADR-0055](../adr/0055-turns-from-the-log.md)). A thread's messages are taken in the log's order, each by one turn: as a run's prompt, as a paused run's reply, or through the watcher of the run that holds the thread. A message or an answer sent with the runner asks for a turn. Whoever holds the thread next, in any process, starts the turn with the oldest message no turn has taken, and its watcher delivers the rest. So a message sent the moment a client sees `run_ended` is answered, and no message is carried out twice.

A message committed without the runner, with `ws.post_message`, asks for nothing, so it starts no turn. The thread's next turn takes it, as its prompt if it is the oldest.

```python
sent = await runner.send(ws, thread.id, "Break the launch into tasks.")
if sent.run is not None:  # None when the thread's run takes the message, or will hand it over
    result = await sent.run.wait()
```

`send` returns a `Sent`: the recorded message (`outcome`, whose `run_id` names the run) and the `RunHandle` it started or resumed, if any. `RunHandle.wait()` returns pydantic-ai's result when the run finishes or pauses. The run's reply is posted to the thread as a `message_posted` event by the agent.

`sent.run` is `None` when the message or answer started no run, which is not a failure:

- the thread's run is already active, in this process or another, so the message steers it; if that run is ending or pausing, it hands the thread over as it releases it, and the next turn takes the message
- another message or answer took the thread first, and its turn takes this one too
- an answer leaves some of the paused run's requests unanswered, so the run waits for them

The run `send` started may take an older message first: the thread's oldest message that no turn has taken.

A message in an idle thread, such as one just created, starts a run unless another starts one first. Code that owns its thread, such as a test or an evaluation, can assert that `sent.run` is set.

`send` takes a `message_id`. Sending a used one again raises `InvalidState` before anything else happens, so a retry never starts or steers a second turn ([ADR-0045](../adr/0045-a-message-id-is-used-once.md)).

| Runner method | What it does |
|---|---|
| `send(workspace, thread_id, content, message_id=None)` | Posts a message and starts, steers or resumes a run |
| `answer(workspace, AnswerDeferred(...))` | Answers one request of a paused run, resuming it once all are answered |
| `resume(workspace, run_id)` | Resumes a paused run whose requests are all answered |
| `stop(run_id)` | Cancels a run in this process; it ends with status `stopped` |
| `drain()` | Waits for the runs that have ended to hand their threads over |
| `aclose()` | Stops every run in this process, as the application shuts down; see [Serving](serving.md#adding-the-router) |
| `watch(run_id)` | Yields the run's live output; see [Live output](live-output.md) |
| `running(thread_id)` | This process's run in a thread, if any |
| `execute(workspace, command, command_id=...)` | Carries out any command the way every surface does, the first time its id is seen, and returns its `command_result`; a repeated id returns the first result |

One run is active per thread. The runner claims the thread with a lease in storage, renewed every third of `claim_ttl` while the run lasts, so the rule holds across processes. A renewal that fails is logged and retried, so a run survives one failed renewal, or storage that stalls for about two thirds of `claim_ttl`; keep it above the clock skew between replicas. A message sent while another process holds the claim steers that run instead of starting a second, or is taken by the turn that run hands the thread over to. Each claim has a holder of its own, so a run resuming cannot renew the claim its pausing segment still holds. Runs are asyncio tasks in the process that started them, so `stop` and `watch` reach only local runs.

A process that dies mid-run cannot record how its run ended, so the run stays `running`. Its claim lapses after `claim_ttl`, and the next run to claim the thread first records the one left behind as failed, with the error "the run was abandoned: its claim lapsed" and the reason `abandoned`, attributed to `SystemActor(name="runner")`. A run the runner starts holds its claim until it has recorded its end, so holding the claim means the other run's process is gone, or its claim lapsed. The abandoned turn is not resumed.

A run whose process lives on loses its claim if no renewal succeeds for a whole `claim_ttl`, even while a renewal hangs, and the runner then cancels it, before another run can claim the thread. If the thread's next run records it as abandoned first, as when its process cannot reach storage to record that it stopped, a tool call it makes is refused, and fails it; the end of a tool already running, and the run's own end, are dropped and logged, so its abandonment is the only end it has.

A runner's `evaluators` judge each turn as it ends, in the background, and record their verdicts as feedback; see [Online evaluation](evaluation.md#online-evaluation).

### Running without a runner

The capability works in any pydantic-ai run. Build the session with `Session.start` and pass the thread's history yourself:

```python
from artifactr.agent import load_history

result = await agent.run(
    "Summarize the plan's open tasks.",
    deps=Session.start(ws, thread.id, app=deps),
    message_history=await load_history(ws, thread.id),
)
```

The run is recorded the same way (with trigger `api`) and its history is saved. The prompt itself is not posted to the thread; post it with `ws.post_message` first if people should see it. A direct run takes no claim: nothing stops two in one thread at once, and a runner that claims the thread meanwhile records the direct run as abandoned. A direct run a runner has recorded as abandoned returns normally if it ends without calling another tool, but its end and history are dropped. If a runner also serves the thread, hold the claim around the run: `async with ws.claim_thread(thread_id, holder=...) as lost:`, and stop the run if the event `lost` is set, as the runner does.

## What is recorded

A run's record is on the log, attributed to the agent:

```text
run_started      trigger: message, resume or api; the trace id when the run is traced
tool_called      for every tool call, the application's included
artifact_changed (or proposal_created, artifact_created, ...) for each change a tool commits
tool_returned    the tool's name, and status: ok, retry (a rejection or the tool's own
                 ModelRetry) or error
message_posted   the agent's reply
run_ended        status: completed (with token usage), stopped or failed (with the error,
                 and a reason when a RunFailure said why)
```

A run that pauses ends its segment with `run_paused` instead, listing the requests it waits on, with the usage so far. A tool or capability that fails the run for a known reason raises `RunFailure(message, reason="...")`: the run is recorded as failed with that `reason`, which clients and dashboards can count on ([ADR-0042](../adr/0042-typed-run-failures.md)). The [LLM gateway](gateway.md) uses it for guardrail blocks. The runner itself records the reason `abandoned`, as the system, for a run whose claim lapsed before it ended (see [Running the agent](#running-the-agent)). The run's new model messages are stored in the same transaction as `run_ended` or `run_paused`, so the history and the log never disagree.

## Proposals

An agent proposes instead of applying a change when:

- the artifact type's `write_policy` is `"propose"`
- the thread is in suggest mode (`SetThreadMode(thread_id=..., mode="suggest")`)
- it asks to, with `edit_text(..., propose=True, rationale=...)` or, in your tools, `submit(workspace, change, propose=True)`

Proposals do not block the run ([ADR-0009](../adr/0009-write-policies-and-non-blocking-proposals.md)). The agent is told its change was proposed and carries on. A person accepts, edits or rejects the proposal from any surface, whenever they like, and the decision reaches the agent as a change note. When a proposal is accepted with edits, the note describes the person's changes. The agent's proposals awaiting review are listed in its instructions.

## Pausing for people

Some points need a person before the agent can continue: a question only they can answer, or an action that needs approval. These use pydantic-ai's deferred tools ([ADR-0010](../adr/0010-pausing-with-deferred-tools.md)):

- `ask_user`, added by `ArtifactWorkspace(..., ask=True)`, asks a question. Any tool that raises `CallDeferred` does the same.
- A tool declared with `requires_approval=True` needs approval before it runs.

The agent's `output_type` must include `DeferredToolRequests`:

```python
from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset, RunContext

release_tools = FunctionToolset[Session[None]]()


@release_tools.tool(requires_approval=True)
async def publish(ctx: RunContext[Session[None]], channel: str) -> str:
    """Publish the release notes to a channel."""
    return f"Published to {channel}."


agent = Agent(
    "anthropic:claude-sonnet-5-5",
    deps_type=Session[None],
    output_type=[str, DeferredToolRequests],
    toolsets=[release_tools],
    capabilities=[ArtifactWorkspace(types=[ReleaseNotes], ask=True)],
)
```

When the model asks a question or calls `publish`, the run ends with a `run_paused` event listing each request (`tool_call_id`, `tool_name`, `kind` of `question` or `approval`, and `args`). Nothing waits in memory, so a pause survives restarts. Answers arrive as `AnswerDeferred` commands, from any surface:

```python
from artifactr.core import AnswerDeferred

run = await ws.run(run_id)
for request in run.pending:
    if request.kind == "question":
        command = AnswerDeferred(run_id=run.id, tool_call_id=request.tool_call_id, answer="Monday")
    else:
        command = AnswerDeferred(run_id=run.id, tool_call_id=request.tool_call_id, approved=True)
    answered = await runner.answer(ws, command)  # resumes the run after the last answer
```

Once every request is answered, the run resumes under the same `run_id`, with the answers passed to pydantic-ai as deferred tool results; an approved call runs then. A chat message sent to a paused thread is the reply, as described above, so the model history never ends in an unanswered tool call.
