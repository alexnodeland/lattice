"""A run's life in the workspace: what is recorded, what the agent is told, and history."""

import asyncio
import logging
import time
from datetime import timedelta
from typing import override

import pytest
from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    FunctionToolset,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelRetry,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior

from artifactr.agent import ArtifactWorkspace, Runner, Session, last_seen, load_history
from artifactr.agent.capability import redacted
from artifactr.core import (
    AgentActor,
    Applied,
    InvalidState,
    Run,
    RunEnded,
    RunStarted,
    RunStatus,
    SystemActor,
    Thread,
    ThreadId,
    ToolCalled,
    ToolReturned,
)
from artifactr.workspace import InMemoryStorage, Scope, Workspace, Workspaces
from tests.agent.conftest import (
    ALICE,
    Gate,
    Script,
    call,
    event_as,
    make_agent,
    make_runner,
    say,
    started,
    types,
)
from tests.artifact_types import Note
from tests.leases import Partitioned


async def test_a_message_starts_a_recorded_run(ws: Workspace, thread: Thread, gate: Gate) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"title": "Plan", "text": "Ship Friday"}),
        say("I drafted the plan."),
    )
    runner = make_runner(make_agent(script), gate)
    handle = (await runner.send(ws, thread.id, "Draft a plan")).run
    assert handle is not None
    assert runner.running(thread.id) == handle
    result = await handle.wait()
    assert result.output == "I drafted the plan."
    assert runner.running(thread.id) is None
    log = await ws.read()
    assert types(log) == [
        "thread_created",
        "message_posted",
        "run_started",
        "tool_called",
        "artifact_created",
        "focus_changed",
        "tool_returned",
        "message_posted",
        "run_ended",
    ]
    agent = AgentActor(thread_id=thread.id, run_id=handle.run_id, on_behalf_of=ALICE)
    assert [e.actor for e in log[2:]] == [agent] * 7, "the run acts for whoever started it"
    [note] = await ws.artifacts(Note)
    assert note.updated_by == agent
    run = await ws.run(handle.run_id)
    assert run.status == "completed"
    ended = log[-1].event
    assert isinstance(ended, RunEnded)
    assert ended.usage is not None
    assert ended.usage.requests == 2
    assert "Ship Friday" in script.instructions(1), "followed artifacts are rendered"
    assert await last_seen(ws, thread.id) == log[-1].seq


async def test_the_next_run_continues_the_conversation(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("Hello!"), say("Still here."))
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Hi")).wait()
    await started(await runner.send(ws, thread.id, "Are you there?")).wait()
    assert script.prompt_texts(1) == ["Hi", "Are you there?"]
    history = await load_history(ws, thread.id)
    assert len(history) == 4


async def test_the_agent_is_told_what_changed_since_it_last_looked(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(
        call("create_artifact", kind="note", data={"text": "Ship Friday"}),
        say("Drafted."),
        say("Noted."),
    )
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Draft")).wait()
    [note] = await ws.artifacts(Note)
    await ws.commit(note.edit_text("Friday", "Monday"))
    await started(await runner.send(ws, thread.id, "I moved the date")).wait()
    notes = [text for text in script.prompt_texts(2) if "<workspace-changes>" in text]
    assert notes == [
        f"<workspace-changes>\n- Alice changed {note.id} (note, v1 → v2): "
        "edited text (1 replacement)\n</workspace-changes>"
    ]


async def test_instructions_describe_the_workspace(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    await ws.create(Note(text="x" * 5000), artifact_id="n1")
    from artifactr.core import SetFocus, SetThreadMode

    await ws.commit(SetFocus(thread_id=thread.id, artifact_ids=("n1",)))
    await ws.commit(SetThreadMode(thread_id=thread.id, mode="suggest"))
    await ws.commit((await ws.get(Note, "n1")).archive())
    script = Script(say("ok"))
    agent = make_agent(script)
    await agent.run("hi", deps=Session.start(ws, thread.id, app=gate))
    instructions = script.instructions(0)
    assert "suggest mode" in instructions
    assert "Kinds of artifact you can create: note, checklist." in instructions
    assert '<artifact id="n1" kind="note" version="2" archived>' in instructions
    assert "x" * 3999 + "…" in instructions


async def test_a_direct_run_watches_from_its_own_start(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(say("ok"))
    session = Session.start(ws, thread.id, app=gate, agent_name="Scribe")
    await make_agent(script).run("hi", deps=session)
    [posted] = [e for e in await ws.read() if e.event.type == "message_posted"]
    assert posted.actor == AgentActor(thread_id=thread.id, run_id=session.run_id, name="Scribe")
    assert session.trigger == "api"


async def test_structured_or_empty_outputs_post_no_message(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    class Summary(BaseModel):
        points: list[str]

    script = Script(call("final_result", points=["a"]))
    agent = make_agent(script, output_type=Summary)
    result = await agent.run("summarize", deps=Session.start(ws, thread.id, app=gate))
    assert result.output == Summary(points=["a"])
    empty = Script(say("  "))
    await make_agent(empty).run("hi", deps=Session.start(ws, thread.id, app=gate))
    assert "message_posted" not in types(await ws.read())


async def test_a_failed_run_is_recorded(ws: Workspace, thread: Thread, gate: Gate) -> None:
    def fail(messages: list[ModelMessage]) -> ModelResponse:
        raise RuntimeError("model unavailable")

    runner = make_runner(make_agent(Script(fail)), gate)
    handle = (await runner.send(ws, thread.id, "hi")).run
    assert handle is not None
    with pytest.raises(RuntimeError):
        await handle.wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.error) == ("failed", "model unavailable")


async def test_a_call_whose_arguments_are_refused_is_recorded_and_retried(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(
        call("create_artifact", call_id="c1", kind="note"),  # no data
        call("create_artifact", call_id="c2", kind="note", data={"text": "Ship Friday"}),
        say("Drafted."),
    )
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Draft a plan")).wait()
    log = await ws.read()
    [called, _] = [event_as(e, ToolCalled) for e in log if isinstance(e.event, ToolCalled)]
    [refused, _] = [event_as(e, ToolReturned) for e in log if isinstance(e.event, ToolReturned)]
    assert (called.tool_call_id, called.args_summary) == ("c1", '{"kind":"note"}')
    assert not called.args_truncated
    assert (refused.tool_call_id, refused.status) == ("c1", "retry")
    assert "data\n  Field required" in refused.summary, "pydantic's error, as the model is told"
    assert event_as(log[-1], RunEnded).status == "completed", "the model was told, and retried"


async def test_a_model_out_of_retries_fails_its_run_for_that_reason(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    script = Script(*[call("create_artifact", kind="note")] * 2)
    runner = make_runner(make_agent(script), gate)
    with pytest.raises(UnexpectedModelBehavior):
        await started(await runner.send(ws, thread.id, "Draft a plan")).wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "tool_retries_exhausted")
    assert "exceeded max retries" in str(ended.error)


async def test_a_model_that_answers_no_way_the_run_takes_fails_for_that_reason(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    class Plan(BaseModel):
        steps: int

    script = Script(*[call("final_result", steps="many")] * 3)  # never a number
    runner = make_runner(make_agent(script, output_type=Plan), gate)
    with pytest.raises(UnexpectedModelBehavior):
        await started(await runner.send(ws, thread.id, "hi")).wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.status, ended.reason) == ("failed", "unexpected_model_behavior")


async def test_a_call_names_the_artifact_it_names_so_it_is_as_hidden(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    note = await ws.create(Note(text="Ship Friday"))
    assert isinstance(note, Applied)
    script = Script(
        call("read_artifact", call_id="c1", artifact_id=note.artifact_id),
        call("read_artifact", call_id="c2", artifact_id="art_none"),
        say("Read."),
    )
    runner = make_runner(make_agent(script), gate)
    await started(await runner.send(ws, thread.id, "Read it")).wait()
    log = await ws.read()
    named = [
        (e.event.type, e.event.artifact_id)
        for e in log
        if isinstance(e.event, ToolCalled | ToolReturned)
    ]
    assert named == [
        ("tool_called", note.artifact_id),
        ("tool_returned", note.artifact_id),
        ("tool_called", "art_none"),
        ("tool_returned", "art_none"),
    ]


async def test_a_capability_told_to_record_no_summaries_records_none(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    note = await ws.create(Note(text="Ship Friday"))
    assert isinstance(note, Applied)
    script = Script(call("read_artifact", artifact_id=note.artifact_id), say("Read."))
    agent = Agent(
        script.model,
        deps_type=Session[Gate],
        capabilities=[ArtifactWorkspace(types=[Note], max_summary_chars=0)],
    )
    await started(await make_runner(agent, gate).send(ws, thread.id, "Read it")).wait()
    calls = [e.event for e in await ws.read() if isinstance(e.event, ToolCalled | ToolReturned)]
    summaries = [c.args_summary if isinstance(c, ToolCalled) else c.summary for c in calls]
    assert summaries == ["", ""]
    cut = [c.args_truncated if isinstance(c, ToolCalled) else c.truncated for c in calls]
    assert cut == [True, True], "each says it was cut short"


async def test_what_a_run_failed_with_is_recorded_without_its_secrets(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    def fail(messages: list[ModelMessage]) -> ModelResponse:
        raise RuntimeError(
            "POST https://u:p@llm.example/v1?api_key=k1 sent Bearer abc sk-0123456789"
        )

    runner = make_runner(make_agent(Script(fail)), gate)
    with pytest.raises(RuntimeError):
        await started(await runner.send(ws, thread.id, "hi")).wait()
    ended = event_as((await ws.read())[-1], RunEnded)
    assert ended.error == "POST https://llm.example/v1 sent Bearer [redacted] [redacted]"


async def test_a_run_left_running_is_abandoned_when_its_thread_is_next_claimed(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    left = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_left"))
    await left.record(RunStarted(run_id="run_left", thread_id=thread.id))  # then its process died
    runner = make_runner(make_agent(Script(say("On it."))), gate)
    handle = started(await runner.send(ws, thread.id, "Are you there?"))
    await handle.wait()
    log = await ws.read()
    assert types(log[3:5]) == ["run_ended", "run_started"], "abandoned before the next run starts"
    assert event_as(log[3], RunEnded) == RunEnded(
        run_id="run_left",
        thread_id=thread.id,
        status="failed",
        error="the run was abandoned: its claim lapsed",
        reason="abandoned",
    )
    assert log[3].actor == SystemActor(name="runner")
    assert await ws.runs(status="running") == [], "so no client is told it is active"
    assert (await ws.run(handle.run_id)).status == "completed"


async def test_recover_abandons_a_run_a_dead_process_left_running(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    left = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_left"))
    await left.record(RunStarted(run_id="run_left", thread_id=thread.id))  # then its process died
    runner = make_runner(make_agent(Script()), gate)
    assert await runner.recover(ws) == [], "nothing was asked for: no turn starts"
    ended = event_as((await ws.read())[-1], RunEnded)
    assert (ended.run_id, ended.status, ended.reason) == ("run_left", "failed", "abandoned")
    assert ended.usage is None, "its usage went with its process"
    assert await ws.runs(status="running") == [], "so no client is told it is active"
    await runner.recover(ws)
    assert types(await ws.read()).count("run_ended") == 1, "ended once"


async def test_recover_sweeps_again_once_a_dead_claim_could_have_lapsed(
    storage: InMemoryStorage, ws: Workspace, thread: Thread, gate: Gate
) -> None:
    """A restart finds the dead process's claim still there, for up to claim_ttl."""
    left = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_left"))
    await left.record(RunStarted(run_id="run_left", thread_id=thread.id))
    scope = Scope(tenant_id=ws.tenant_id, workspace_id=ws.workspace_id)
    dead = timedelta(milliseconds=150)
    assert await storage.acquire_lease(scope, f"thread:{thread.id}", "dead-process", dead)
    runner = Runner(make_agent(Script()), app=gate, look_again_after=timedelta(milliseconds=200))
    assert await runner.recover(ws) == []
    assert (await ws.run("run_left")).status == "running", "its claim hasn't lapsed yet"
    await asyncio.gather(*runner._looks)  # the look again, once the dead claim could lapse
    assert (await ws.run("run_left")).status == "failed", "swept again once it could have"
    await runner.aclose()


async def test_a_sweep_waiting_to_look_again_is_cancelled_as_the_runner_closes(
    storage: InMemoryStorage, ws: Workspace, thread: Thread, gate: Gate
) -> None:
    left = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_left"))
    await left.record(RunStarted(run_id="run_left", thread_id=thread.id))
    scope = Scope(tenant_id=ws.tenant_id, workspace_id=ws.workspace_id)
    assert await storage.acquire_lease(scope, f"thread:{thread.id}", "dead", timedelta(seconds=5))
    runner = Runner(make_agent(Script()), app=gate, look_again_after=timedelta(seconds=5))
    await runner.recover(ws)
    await runner.aclose()
    assert (await ws.run("run_left")).status == "running", "left to the next process"


async def test_recover_leaves_a_run_another_process_holds(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    running = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_live"))
    runner = make_runner(make_agent(Script()), gate)
    async with ws.claim_thread(thread.id, holder="run_live"):
        await running.record(RunStarted(run_id="run_live", thread_id=thread.id))
        assert await runner.recover(ws) == []
    assert (await ws.run("run_live")).status == "running"


async def test_recover_leaves_this_processs_own_runs(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold"), say("Done.")), tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Go"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    assert await runner.recover(ws) == []
    gate.release.set()
    assert (await handle.wait()).output == "Done."


async def test_a_run_whose_claim_is_held_is_not_abandoned(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    running = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_live"))
    runner = make_runner(make_agent(Script()), gate)
    async with ws.claim_thread(thread.id, holder="run_live"):
        await running.record(RunStarted(run_id="run_live", thread_id=thread.id))
        assert (await runner.send(ws, thread.id, "Also this")).run is None, "it steers the run"
    assert (await ws.run("run_live")).status == "running"


class SlowRunningReads(InMemoryStorage):
    """Storage whose reads of running runs wait until the test lets them go."""

    def __init__(self) -> None:
        super().__init__()
        self.reading = asyncio.Event()
        self.go = asyncio.Event()

    @override
    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        if status == "running":
            self.reading.set()
            await self.go.wait()
        return await super().runs(scope, thread_id=thread_id, status=status)


async def test_a_start_cancelled_while_abandoning_releases_the_claim(gate: Gate) -> None:
    storage = SlowRunningReads()
    ws = await Workspaces(storage).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = make_runner(make_agent(Script()), gate)
    sending = asyncio.create_task(runner.send(ws, thread.id, "hi"))
    await asyncio.wait_for(storage.reading.wait(), timeout=2)
    sending.cancel()
    await asyncio.gather(sending, return_exceptions=True)
    await runner.aclose()  # and with it the hand-over the cancelled start spawned
    async with ws.claim_thread(thread.id, holder="next"):
        pass


async def test_a_runner_closed_while_abandoning_starts_no_run(gate: Gate) -> None:
    storage = SlowRunningReads()
    ws = await Workspaces(storage).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = make_runner(make_agent(Script()), gate)
    sending = asyncio.create_task(runner.send(ws, thread.id, "hi"))
    await asyncio.wait_for(storage.reading.wait(), timeout=2)
    await runner.aclose()
    storage.go.set()
    assert (await sending).run is None
    async with ws.claim_thread(thread.id, holder="next"):
        pass


class StaleRunningReads(InMemoryStorage):
    """Storage whose reads of running runs are stale: they list runs that have since ended."""

    @override
    async def runs(
        self, scope: Scope, *, thread_id: ThreadId | None = None, status: RunStatus | None = None
    ) -> list[Run]:
        stale = status == "running"
        return await super().runs(scope, thread_id=thread_id, status=None if stale else status)


async def test_a_run_that_ended_meanwhile_is_left_as_it_ended(gate: Gate) -> None:
    ws = await Workspaces(StaleRunningReads()).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    agent = ws.as_actor(AgentActor(thread_id=thread.id, run_id="run_done"))
    await agent.record(RunStarted(run_id="run_done", thread_id=thread.id))
    await agent.record(RunEnded(run_id="run_done", thread_id=thread.id, status="completed"))
    runner = make_runner(make_agent(Script(say("On it."))), gate)
    await started(await runner.send(ws, thread.id, "Are you there?")).wait()
    assert (await ws.run("run_done")).status == "completed"


async def test_a_run_whose_claim_lapses_is_stopped_at_its_deadline(
    gate: Gate, app_tools: FunctionToolset[Session[Gate]], caplog: pytest.LogCaptureFixture
) -> None:
    # A claim ttl a test outlasts. The claim survives a stall of up to about two thirds of it, so
    # a slow start doesn't lose it.
    ttl = timedelta(seconds=2)
    storage = Partitioned(in_flight=True)
    ws = await Workspaces(storage).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    runner = Runner(make_agent(Script(call("hold")), tools=[app_tools]), app=gate, claim_ttl=ttl)
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    async with asyncio.timeout(5):
        await gate.entered.wait()
    # Only once the run holds its tool: its next renewal hangs, and its claim lapses.
    storage.cut_off.add(storage.holders[f"thread:{thread.id}"])
    async with asyncio.timeout(2 * ttl.total_seconds()):
        await asyncio.gather(handle.task, return_exceptions=True)
    assert handle.task.cancelled()
    assert types(await ws.read()) == [
        "thread_created",
        "message_posted",
        "run_started",
        "tool_called",
        "run_ended",
    ]
    assert (await ws.run(handle.run_id)).status == "stopped", "nothing is left to abandon"
    async with ws.claim_thread(thread.id, holder="next"):
        pass
    assert f"the claim thread:{thread.id} lapsed, so it is lost" in caplog.text


async def test_an_abandoned_run_calls_no_more_tools(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    app_tools: FunctionToolset[Session[Gate]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="artifactr")
    script = Script(call("hold"), call("create_artifact", "call_2", kind="note", data={}))
    runner = make_runner(make_agent(script, tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Hold on, then take a note"))
    async with asyncio.timeout(5):
        await gate.entered.wait()
    abandoned = RunEnded(run_id=handle.run_id, thread_id=thread.id, status="failed")
    await ws.as_actor(SystemActor(name="runner")).record(abandoned)
    gate.release.set()  # the tool already running finishes
    with pytest.raises(InvalidState, match="is failed"):
        await handle.wait()
    assert await ws.artifacts() == [], "the next tool call is refused"
    assert types(await ws.read())[-2:] == ["tool_called", "run_ended"], "and nothing is recorded"
    for dropped in ("tool_returned", "run_ended"):
        assert f"the {dropped} of a run that has failed is dropped" in caplog.text


async def test_a_run_ended_otherwise_meanwhile_fails(
    ws: Workspace, thread: Thread, gate: Gate, app_tools: FunctionToolset[Session[Gate]]
) -> None:
    runner = make_runner(make_agent(Script(call("hold")), tools=[app_tools]), gate)
    handle = started(await runner.send(ws, thread.id, "Hold on"))
    async with asyncio.timeout(5):
        await gate.entered.wait()
    stopped = RunEnded(run_id=handle.run_id, thread_id=thread.id, status="stopped")
    await ws.as_actor(SystemActor(name="ops")).record(stopped)
    gate.release.set()
    with pytest.raises(InvalidState, match="is stopped"):
        await handle.wait()


async def test_an_unwatched_failure_does_not_warn(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    def fail(messages: list[ModelMessage]) -> ModelResponse:
        raise RuntimeError("boom")

    runner = make_runner(make_agent(Script(fail)), gate)
    handle = (await runner.send(ws, thread.id, "hi")).run
    assert handle is not None
    # Wait for the task's done callbacks without awaiting it, which would retrieve its failure.
    # A task is done one turn of the loop before they run, and they run in the order they were
    # added, so the runner's own, which forgets the run and retrieves its failure, runs first.
    ended = asyncio.Event()
    handle.task.add_done_callback(lambda _: ended.set())
    await ended.wait()
    assert runner.running(thread.id) is None


def test_history_messages_are_model_requests_first() -> None:
    assert ModelRequest.kind == "request"


BOT_ID = "1" * 9
BOT_KEY = "AA" + "x" * 33


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("Authorization: Basic dXNlcjpwYXNz", "Authorization: Basic [redacted]"),
        ("failed with api_key=abc123 set", "failed with api_key=[redacted] set"),
        ('{"token": "t0k3n", "n": 1}', '{"token": "[redacted]", "n": 1}'),
        ("password: hunter2", "password: [redacted]"),
        ("used ghp_abcdefghijklmnopqrstuvwxyz0123", "used [redacted]"),
        ("used github_pat_11AAAAAAAAAAAAAAAAAAAAAA_b", "used [redacted]"),
        ("jwt eyJhbGci.eyJzdWIi.c2ln", "jwt [redacted]"),
        ("no artifact art_1", "no artifact art_1"),
        ("client_secret=s3cr3t&x", "client_secret=[redacted]"),
        ("OPENAI_API_KEY=abc123 missing", "OPENAI_API_KEY=[redacted] missing"),
        ("SECRET_KEY: abc", "SECRET_KEY: [redacted]"),
        ('{"refresh_token": "r1"}', '{"refresh_token": "[redacted]"}'),
        ("db_password=hunter2", "db_password=[redacted]"),
        ("max_tokens=1000 reached", "max_tokens=1000 reached"),
        ("token_count=12 used", "token_count=12 used"),
        ("apiKey=abc", "apiKey=[redacted]"),
        # A secret all digits, or digits first, is a secret still.
        ("password=123456", "password=[redacted]"),
        ('{"password": "123456"}', '{"password": "[redacted]"}'),
        ("api_key=1234567890123456", "api_key=[redacted]"),
        # A bot token's shape, a number and a key, put together here so no whole one is written.
        (f"token={BOT_ID}:{BOT_KEY}", "token=[redacted]"),
        ("secret=123.hunter2", "secret=[redacted]"),
        ("password=1.5x", "password=[redacted]"),
        ("password=123-456", "password=[redacted]"),
        # A name that only has a secret's word inside a longer word isn't a secret's.
        ("secretary: John", "secretary: John"),
        ("tokenizer: gpt2", "tokenizer: gpt2"),
        ("passwordless: true", "passwordless: true"),
        ("max_tokens=unlimited", "max_tokens=unlimited"),
        ("tokenCount=12", "tokenCount=12"),
        ("maxtokens=12", "maxtokens=12"),
        # A long name, and names whose words are run together, are a secret's still.
        ("x" * 65 + "_password=abc", "x" * 65 + "_password=[redacted]"),
        ("CLIENTSECRET=abc", "CLIENTSECRET=[redacted]"),
        ("ACCESSTOKEN=abc", "ACCESSTOKEN=[redacted]"),
        ("APIKEY=abc", "APIKEY=[redacted]"),
    ],
)
def test_what_looks_like_a_secret_is_redacted(text: str, kept: str) -> None:
    assert redacted(text) == kept


@pytest.mark.parametrize(
    argnames="text",
    ids=["hyphens", "underscores", "a-a", "a-a-a", "spaces", "urls", "a long name", "a long run"],
    argvalues=[
        "token-" * 5000,
        "token_" * 5000,
        "a-" * 15000,
        "a-a-a-" * 5000,
        "password " * 5000,
        "a://" * 8000,
        "x" * 100_000 + "=",
        "a-" * 50_000 + "_password",
    ],
)
def test_redaction_takes_time_in_line_with_the_text(text: str) -> None:
    started = time.perf_counter()
    redacted(text)
    assert time.perf_counter() - started < 0.5


async def test_a_tools_own_refusal_is_recorded_without_its_secrets(
    ws: Workspace, thread: Thread, gate: Gate
) -> None:
    tools = FunctionToolset[Session[Gate]]()

    @tools.tool_plain
    async def fetch() -> str:
        """Fetch something."""
        raise ModelRetry("GET https://api.example/x?token=s3cret refused")

    script = Script(call("fetch"), say("Gave up."))
    await started(
        await make_runner(make_agent(script, tools=[tools]), gate).send(ws, thread.id, "Go")
    ).wait()
    [returned] = [e.event for e in await ws.read() if isinstance(e.event, ToolReturned)]
    assert returned.summary == "GET https://api.example/x refused"
