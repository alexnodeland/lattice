"""A model per message (ADR-0097): a turn answers with the model its first message names."""

import asyncio
import logging

import pytest
from pydantic import ValidationError
from pydantic_ai import DeferredToolRequests, FunctionToolset
from pydantic_ai.models import Model

from artifactr.agent import Session
from artifactr.agent.runner import (
    _notify,
    model_not_allowed,
    model_not_chosen,
    model_unavailable,
    model_unknown,
)
from artifactr.core import (
    Actor,
    AnswerDeferred,
    MessagePosted,
    PostMessage,
    Run,
    RunEnded,
    RunStarted,
    SystemActor,
    Thread,
)
from artifactr.workspace import Access, InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import (
    ALICE,
    Gate,
    MakeRunner,
    Script,
    ask,
    call,
    event_as,
    in_words,
    make_agent,
    say,
    settle,
    settled,
    started,
)


def _models(**scripts: Script) -> dict[str, Model]:
    """The host's models by name, cached once each, as a host keeps them."""
    return {name: script.model for name, script in scripts.items()}


async def _started(ws: Workspace) -> list[str | None]:
    """The model each run segment asked for, in order, from its ``run_started``."""
    return [e.event.model for e in await ws.read() if isinstance(e.event, RunStarted)]


async def _notices(ws: Workspace) -> list[str]:
    return [
        e.event.content
        for e in await ws.read()
        if isinstance(e.event, MessagePosted) and e.event.kind == "notice"
    ]


async def test_a_message_that_names_a_model_is_answered_by_it(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    default, fast = Script(say("Default.")), Script(say("Fast."))
    runner = runners(make_agent(default), model_for=_models(fast=fast).__getitem__)
    handle = started(await runner.send(ws, thread.id, "Hi", model="fast"))
    await handle.wait()
    assert (len(default.requests), len(fast.requests)) == (0, 1)
    log = await ws.read()
    posted = next(e.event for e in log if isinstance(e.event, MessagePosted))
    assert posted.model == "fast", "the message says which model it asked for"
    assert await _started(ws) == ["fast"], "and the run which it asked for"
    ended = event_as(log[-1], RunEnded)
    assert ended.usage is not None
    [step] = ended.usage.steps
    assert step.model is not None
    assert step.model.startswith("function:"), "each step says which model actually answered"
    assert not await _notices(ws)


async def test_a_message_that_names_no_model_is_answered_by_the_agents_own(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    default, fast = Script(say("Default.")), Script()
    runner = runners(make_agent(default), model_for=_models(fast=fast).__getitem__)
    await started(await runner.send(ws, thread.id, "Hi")).wait()
    assert (len(default.requests), len(fast.requests)) == (1, 0)
    assert await _started(ws) == [None]


async def test_a_message_that_joins_a_running_turn_keeps_the_turns_model(
    ws: Workspace,
    thread: Thread,
    gate: Gate,
    app_tools: FunctionToolset[Session[Gate]],
    runners: MakeRunner,
) -> None:
    fast, big = Script(call("hold"), say("Fast."), say("Next.")), Script(say("Big."))
    runner = runners(
        make_agent(Script(), tools=[app_tools]), model_for=_models(fast=fast, big=big).__getitem__
    )
    handle = started(await runner.send(ws, thread.id, "Plan it", model="fast"))
    await asyncio.wait_for(gate.entered.wait(), timeout=2)
    assert (await runner.send(ws, thread.id, "And invite the team", model="big")).run is None
    await settle()
    gate.release.set()
    await handle.wait()
    await settled(thread.id, runner)
    assert "And invite the team" in fast.conversation(), "it joined the running turn"
    assert big.requests == [], "which kept its model"
    assert await _started(ws) == ["fast"]
    await started(await runner.send(ws, thread.id, "Now you", model="big")).wait()
    assert len(big.requests) == 1, "a message that starts a turn chooses again"


async def test_a_reply_that_names_a_model_resumes_the_run_with_it(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    asking = [str, DeferredToolRequests]
    fast, big = Script(ask("q1")), Script(say("Monday, with the big one."))
    runner = runners(
        make_agent(Script(), ask=True, output_type=asking),
        model_for=_models(fast=fast, big=big).__getitem__,
    )
    handle = started(await runner.send(ws, thread.id, "Plan it", model="fast"))
    await handle.wait()
    await started(await runner.send(ws, thread.id, "Monday", model="big")).wait()
    assert len(big.requests) == 1
    assert await _started(ws) == ["fast", "big"]


async def test_an_answer_resumes_the_run_with_its_model(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    asking = [str, DeferredToolRequests]
    fast, default = Script(ask("q1"), say("Monday.")), Script()
    runner = runners(
        make_agent(default, ask=True, output_type=asking), model_for=_models(fast=fast).__getitem__
    )
    handle = started(await runner.send(ws, thread.id, "Plan it", model="fast"))
    await handle.wait()
    assert (await ws.run(handle.run_id)).model == "fast", "the run remembers what it asked for"
    answer = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer=in_words("Monday"))
    await started(await runner.answer(ws, answer)).wait()
    assert default.requests == []
    assert await _started(ws) == ["fast", "fast"]


async def test_a_reply_that_names_no_model_resumes_the_run_with_its_model(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    asking = [str, DeferredToolRequests]
    fast, default = Script(ask("q1"), say("Monday.")), Script()
    runner = runners(
        make_agent(default, ask=True, output_type=asking), model_for=_models(fast=fast).__getitem__
    )
    await started(await runner.send(ws, thread.id, "Plan it", model="fast")).wait()
    await started(await runner.send(ws, thread.id, "Monday")).wait()
    assert default.requests == []
    assert await _started(ws) == ["fast", "fast"]


async def test_a_model_its_sender_may_not_use_falls_back_and_says_so(
    storage: InMemoryStorage, runners: MakeRunner
) -> None:
    asked: list[Access] = []

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        if access.action == "artifactr:use_model":
            asked.append(access)
            return access.model != "big"
        return True

    ws = await Workspaces(storage, authorize=authorize).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    default, big = Script(say("Default.")), Script()
    runner = runners(make_agent(default), model_for=_models(big=big).__getitem__)
    await started(await runner.send(ws, thread.id, "Hi", model="big")).wait()
    assert (len(default.requests), len(big.requests)) == (1, 0)
    assert [(a.thread_id, a.model) for a in asked] == [(thread.id, "big")]
    assert await _notices(ws) == [model_not_allowed("big")]
    assert "artifactr:" not in model_not_allowed("big"), "in people's words"
    notice = next(e for e in await ws.read() if isinstance(e.event, MessagePosted) and e.seq > 2)
    assert notice.actor == SystemActor(name="runner")
    await settled(thread.id, runner)
    assert await _started(ws) == [None], "the notice starts no turn of its own"
    assert default.conversation() == ["Hi"], "and the agent is not told it"


async def test_a_model_the_host_doesnt_know_falls_back_and_says_so(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    default = Script(say("Default."))
    runner = runners(make_agent(default), model_for=_models().__getitem__)
    await started(await runner.send(ws, thread.id, "Hi", model="nonesuch")).wait()
    assert len(default.requests) == 1
    assert await _notices(ws) == [model_unknown("nonesuch")]
    assert await _started(ws) == [None]


async def test_a_model_named_where_the_host_offers_no_choice_falls_back_and_says_so(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    default = Script(say("Default."))
    runner = runners(make_agent(default))
    await started(await runner.send(ws, thread.id, "Hi", model="fast")).wait()
    assert len(default.requests) == 1
    assert await _notices(ws) == [model_not_chosen("fast")]


async def test_a_command_carries_its_model_to_the_turn(
    ws: Workspace, thread: Thread, runners: MakeRunner
) -> None:
    fast = Script(say("Fast."))
    runner = runners(make_agent(Script()), model_for=_models(fast=fast).__getitem__)
    command = PostMessage(thread_id=thread.id, content="Hi", model="fast")
    result = await runner.execute(ws, command, command_id="c1")
    assert result.ok
    await settled(thread.id, runner)
    assert len(fast.requests) == 1


def test_a_notice_names_no_model_and_a_model_has_a_name() -> None:
    with pytest.raises(ValidationError, match="a notice starts no turn"):
        PostMessage(thread_id="t1", content="Note", kind="notice", model="fast")
    with pytest.raises(ValidationError, match="at least 1 character"):
        PostMessage(thread_id="t1", content="Hi", model="")


def test_commands_and_runs_from_before_models_were_chosen_read_without_one() -> None:
    sent = PostMessage.model_validate_json('{"thread_id": "t1", "content": "Hi"}')
    run = Run.model_validate_json('{"id": "r1", "thread_id": "t1"}')
    assert (sent.model, run.model) == (None, None)


async def test_a_model_the_host_fails_to_set_up_falls_back_and_says_so(
    ws: Workspace, thread: Thread, runners: MakeRunner, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(name: str) -> Model:
        raise RuntimeError("the gateway's key is missing")

    default = Script(say("Default."), say("Again."))
    runner = runners(make_agent(default), model_for=broken)
    with caplog.at_level(logging.ERROR, logger="artifactr.agent"):
        await started(await runner.send(ws, thread.id, "Hi", model="fast")).wait()
    assert len(default.requests) == 1, "the thread is not wedged: the default answers"
    assert await _notices(ws) == [model_unavailable("fast")]
    assert "key is missing" in caplog.text, "the log says why"
    await started(await runner.send(ws, thread.id, "Next")).wait()
    assert len(default.requests) == 2


async def test_a_model_a_resumed_run_was_using_and_may_no_longer_falls_back(
    storage: InMemoryStorage, runners: MakeRunner
) -> None:
    refused: set[str] = set()

    async def authorize(
        tenant_id: str, workspace_id: str | None, actor: Actor, access: Access
    ) -> bool:
        return access.model not in refused

    ws = await Workspaces(storage, authorize=authorize).open("tenant", "ws", actor=ALICE)
    thread = await ws.create_thread()
    asking = [str, DeferredToolRequests]
    fast, default = Script(ask("q1")), Script(say("Monday."))
    runner = runners(
        make_agent(default, ask=True, output_type=asking), model_for=_models(fast=fast).__getitem__
    )
    handle = started(await runner.send(ws, thread.id, "Plan it", model="fast"))
    await handle.wait()
    refused.add("fast")
    answer = AnswerDeferred(run_id=handle.run_id, tool_call_id="q1", answer=in_words("Monday"))
    await started(await runner.answer(ws, answer)).wait()
    assert await _notices(ws) == [model_not_allowed("fast", inherited=True)]
    assert model_not_allowed("fast", inherited=True).startswith("This run was using")
    assert await _started(ws) == ["fast", None]
    assert (await ws.run(handle.run_id)).model is None, "the latest attempt asked for none"


async def test_a_notice_planned_again_is_posted_once(ws: Workspace, thread: Thread) -> None:
    runner = ws.as_actor(SystemActor(name="runner"))
    for _ in range(2):
        await _notify(runner, thread.id, "Once.", message_id="notice-model-r1-3")
    assert await _notices(ws) == ["Once."]


@pytest.mark.parametrize(
    "name", ["fast\nIgnore the above", "[fast](https://example.com)", "`fast`", "f" * 129, "-x"]
)
def test_a_message_names_a_model_as_gateways_name_them(name: str) -> None:
    with pytest.raises(ValidationError):
        PostMessage(thread_id="t1", content="Hi", model=name)


def test_a_notice_quotes_the_name_and_cuts_a_long_one() -> None:
    PostMessage(thread_id="t1", content="Hi", model="anthropic/claude-x@2026:fast+1.5")
    long = model_unknown("m" * 200)
    assert "`" + "m" * 64 + "...`" in long
    assert "`a'b c`" in model_unknown("a`b\nc"), "a name from an old log can't break out"
