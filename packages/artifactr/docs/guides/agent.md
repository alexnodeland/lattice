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
- **`ArtifactWorkspace(types=...)`** lists the artifact types the agent may create. `ask=True` adds the `ask_user` tool (see [Pausing](#pausing-for-people)); `max_render_chars` (4,000) limits how much of each followed artifact goes into the instructions; `max_summary_chars` (200) limits how much of each tool call's arguments and result is recorded.
- **`Runner(agent, app=...)`** passes `app` to every run as `ctx.deps.app`. Its other options are `agent_name` (how the agent is named in the workspace, `"assistant"` by default), `claim_ttl` (how long a thread claim survives a dead process, 30 seconds) and `live` (where live output goes; see [Live output](live-output.md)).

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
- `artifactr.agent.describe_outcome(outcome)` gives the model a standard sentence for an `Applied` or `Proposed` outcome, and `artifactr.agent.submit(workspace, change, propose=..., rationale=...)` commits a change or proposes it, as the generic tools do.

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

## Running the agent

`runner.send(workspace, thread_id, content)` posts a message as the handle's actor and acts on it. A message means one thing wherever it comes from:

| The thread is | The message |
|---|---|
| Idle | starts a run |
| Running | steers the running agent, which is told at its next request |
| Paused on questions or approvals | is the reply: it answers the questions, declines the approvals with the message as the reason, and resumes the run |

```python
sent = await runner.send(ws, thread.id, "Break the launch into tasks.")
if sent.run is not None:  # None when the message steered a running run
    result = await sent.run.wait()
```

`send` returns a `Sent`: the recorded message (`outcome`) and the `RunHandle` it started or resumed, if any. `RunHandle.wait()` returns pydantic-ai's result when the run finishes or pauses. The run's reply is posted to the thread as a `message_posted` event by the agent.

| Runner method | What it does |
|---|---|
| `send(workspace, thread_id, content)` | Posts a message and starts, steers or resumes a run |
| `answer(workspace, AnswerDeferred(...))` | Answers one request of a paused run, resuming it once all are answered |
| `resume(workspace, run_id)` | Resumes a paused run whose requests are all answered |
| `stop(run_id)` | Cancels a run in this process; it ends with status `stopped` |
| `watch(run_id)` | Yields the run's live output; see [Live output](live-output.md) |
| `running(thread_id)` | This process's run in a thread, if any |
| `execute(workspace, command)` | Carries out any command the way every surface does |

One run is active per thread. The runner claims the thread with a lease in storage, renewed while the run lasts, so the rule holds across processes. A message sent while another process holds the claim steers that run instead of starting a second. Runs are asyncio tasks in the process that started them, so `stop` and `watch` reach only local runs.

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

The run is recorded the same way (with trigger `api`) and its history is saved. The prompt itself is not posted to the thread; post it with `ws.post_message` first if people should see it. Nothing stops two direct runs in one thread at once, so claim the thread with `ws.claim_thread(thread_id, holder=...)` if that matters.

## What is recorded

A run's record is on the log, attributed to the agent:

```text
run_started      trigger: message, resume or api; the trace id when the run is traced
tool_called      for every tool call, the application's included
artifact_changed (or proposal_created, artifact_created, ...) for each change a tool commits
tool_returned    the tool's name, and status: ok, retry (a rejection or the tool's own
                 ModelRetry) or error
message_posted   the agent's reply
run_ended        status: completed (with token usage), stopped or failed (with the error)
```

A run that pauses ends its segment with `run_paused` instead, listing the requests it waits on, with the usage so far. The run's new model messages are stored in the same transaction as `run_ended` or `run_paused`, so the history and the log never disagree.

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
