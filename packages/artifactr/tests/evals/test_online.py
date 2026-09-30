"""Online evaluation: evalr's evaluators judge turns after they end, and give feedback."""

import asyncio
import logging
from typing import Any, cast

import pytest
from pydantic import BaseModel
from pydantic_ai import DeferredToolRequests

from artifactr.agent import EndedTurn, Runner
from artifactr.core import (
    EvaluatorActor,
    FeedbackGiven,
    Thread,
    ThreadTarget,
    TurnTarget,
)
from artifactr.evals import OnlineEvaluator, TargetContext, TaskCompletion, completion_transcript
from artifactr.workspace import Workspace
from evalr.core import FunctionEvaluator, HandOff, Verdict
from evalr.measures import Transcript
from evalr.memory import InMemoryScoreSink
from evalr.online import Budget, OnlineResult
from tests.agent.conftest import Gate, Script, call, make_agent, say, started
from tests.artifact_types import Accuracy, Helpfulness
from tests.evals.conftest import Said, said
from tests.telemetry.conftest import Recorder, trace_id


def build(context: TargetContext) -> Said:
    return Said(said=said(context.transcript))


def helpful(judged: Said) -> Helpfulness:
    return Helpfulness(rating=5 if judged.said[-1].endswith("Done.") else 2)


def judge(recorder: Recorder, name: str = "helpful") -> FunctionEvaluator[Said, Helpfulness]:
    return FunctionEvaluator(
        helpful,
        verdict_type=Helpfulness,
        name=name,
        version="1",
        tracer_provider=recorder.tracer_provider,
    )


class Kept:
    """Forwards turns to an online evaluator, keeping the evaluations it starts."""

    def __init__(self, online: OnlineEvaluator[Any]) -> None:
        self.online = online
        self.started: list[asyncio.Task[OnlineResult]] = []

    def submit(self, turn: EndedTurn) -> None:
        task = self.online.submit(turn)
        if task is not None:
            self.started.append(task)

    async def results(self) -> list[OnlineResult]:
        """Every evaluation's result, oldest first, once all have finished."""
        await self.online.drain()
        return [task.result() for task in self.started]


async def verdicts(workspace: Workspace) -> list[tuple[str, FeedbackGiven]]:
    return [
        (envelope.actor.participant, envelope.event)
        for envelope in await workspace.read()
        if isinstance(envelope.event, FeedbackGiven)
    ]


async def test_turns_are_judged_as_they_end_and_verdicts_are_feedback(
    traced: Workspace, recorder: Recorder
) -> None:
    thread = await traced.create_thread("Launch")
    sink = InMemoryScoreSink()
    online = OnlineEvaluator([judge(recorder)], input=build, sinks=[sink])
    kept = Kept(online)
    runner = Runner(
        make_agent(Script(say("Done."))), app=Gate(), evaluators=[kept], **recorder.providers
    )
    handle = started(await runner.send(traced, thread.id, "Draft"))
    await handle.wait()
    [result] = await kept.results()
    assert (result.key, result.errors) == (handle.run_id, ())
    assert await verdicts(traced) == [
        (
            "evaluator:helpful@1",
            FeedbackGiven(
                feedback_type="helpfulness",
                target=TurnTarget(run_id=handle.run_id),
                value={"rating": 5, "reason": None},
                thread_id=thread.id,
                run_id=handle.run_id,
            ),
        )
    ]
    assert [score.name for score in sink.scores.values()] == ["helpfulness.rating"]
    # The evaluation, and the feedback it gave, are in the turn's trace.
    turn = trace_id(recorder.span("invoke_workflow turn"))
    assert trace_id(recorder.span("evalr.evaluate helpful")) == turn
    assert trace_id(recorder.span("artifactr.commit give_feedback")) == turn


async def test_evaluation_never_holds_up_the_turn(traced: Workspace, recorder: Recorder) -> None:
    thread = await traced.create_thread("Launch")
    release = asyncio.Event()

    async def slow(judged: Said) -> Helpfulness:
        await release.wait()
        return helpful(judged)

    online = OnlineEvaluator(
        [FunctionEvaluator(slow, verdict_type=Helpfulness, name="slow")], input=build
    )
    runner = Runner(make_agent(Script(say("Done."))), app=Gate(), evaluators=[online])
    handle = started(await runner.send(traced, thread.id, "Draft"))
    await handle.wait()
    assert runner.running(thread.id) is None
    assert await verdicts(traced) == []
    release.set()
    await online.drain()
    assert [who for who, _ in await verdicts(traced)] == ["evaluator:slow@1"]


async def test_failures_are_recorded_and_the_turn_goes_on(
    traced: Workspace, recorder: Recorder, caplog: pytest.LogCaptureFixture
) -> None:
    thread = await traced.create_thread("Launch")

    def broken(judged: Said) -> Helpfulness:
        raise RuntimeError("the judge is down")

    def unsure(judged: Said) -> Helpfulness:
        raise HandOff

    def wrong_target(judged: Said) -> Accuracy:
        return Accuracy(correct=True)

    online = OnlineEvaluator(
        [
            FunctionEvaluator(broken, verdict_type=Helpfulness),
            FunctionEvaluator(unsure, verdict_type=Helpfulness),
            FunctionEvaluator(wrong_target, verdict_type=Accuracy),
            judge(recorder),
        ],
        input=build,
    )
    kept = Kept(online)
    runner = Runner(make_agent(Script(say("Done."))), app=Gate(), evaluators=[kept])
    with caplog.at_level(logging.WARNING, logger="artifactr.evals"):
        handle = started(await runner.send(traced, thread.id, "Draft"))
        await handle.wait()
        [result] = await kept.results()
    assert (await traced.run(handle.run_id)).status == "completed"
    assert result.handed_off == ("unsure",)
    assert result.errors == (
        "broken: RuntimeError: the judge is down",
        "wrong_target: ValidationFailed: accuracy feedback is given on artifact, not on a turn",
    )
    assert [who for who, _ in await verdicts(traced)] == ["evaluator:helpful@1"]
    assert [record.getMessage() for record in caplog.records] == [
        f"evaluating run {handle.run_id} failed: {error}" for error in result.errors
    ]


async def test_an_input_that_cannot_be_built_is_a_recorded_failure(
    traced: Workspace, recorder: Recorder
) -> None:
    thread = await traced.create_thread("Launch")

    async def unbuildable(context: TargetContext) -> Said:
        raise LookupError("no transcript")

    kept = Kept(OnlineEvaluator([judge(recorder)], input=unbuildable))
    runner = Runner(make_agent(Script(say("Done."))), app=Gate(), evaluators=[kept])
    handle = started(await runner.send(traced, thread.id, "Draft"))
    await handle.wait()
    [result] = await kept.results()
    assert (result.key, result.sampled) == (handle.run_id, True)
    assert result.errors == ("input: LookupError: no transcript",)
    assert await verdicts(traced) == []


class Plain(BaseModel):
    good: bool


class Impostor:
    """An evaluator that claims to give feedback, but gives a plain model."""

    name = "impostor"
    version = "1"
    verdict_type = Helpfulness

    async def evaluate(self, input: Said, /) -> Verdict[Helpfulness]:
        plain = Verdict[Plain](value=Plain(good=True), evaluator=self.name, version=self.version)
        return cast(Verdict[Helpfulness], plain)


async def test_a_verdict_that_is_not_feedback_is_a_recorded_failure(
    traced: Workspace, recorder: Recorder
) -> None:
    thread = await traced.create_thread("Launch")
    kept = Kept(OnlineEvaluator([Impostor()], input=build))
    runner = Runner(make_agent(Script(say("Done."))), app=Gate(), evaluators=[kept])
    await started(await runner.send(traced, thread.id, "Draft")).wait()
    [result] = await kept.results()
    assert result.errors == ("impostor: TypeError: Plain is not a feedback type",)


async def test_only_sampled_turns_that_ended_as_asked_are_judged(
    traced: Workspace, recorder: Recorder
) -> None:
    thread = await traced.create_thread("Launch")
    asking = make_agent(
        Script(call("ask_user", question="Which day?"), say("Done.")),
        ask=True,
        output_type=[str, DeferredToolRequests],
    )
    completed = OnlineEvaluator([judge(recorder)], input=build)
    paused = OnlineEvaluator([judge(recorder, "on-pause")], input=build, outcomes={"paused"})
    never = OnlineEvaluator([judge(recorder, "never")], input=build, sample_rate=0.0)
    runner = Runner(asking, app=Gate(), evaluators=[completed, paused, never])
    await started(await runner.send(traced, thread.id, "Plan")).wait()
    await started(await runner.send(traced, thread.id, "Monday")).wait()
    await asyncio.gather(completed.drain(), paused.drain(), never.drain())
    assert [who for who, _ in await verdicts(traced)] == [
        "evaluator:on-pause@1",
        "evaluator:helpful@1",
    ]


async def test_a_budget_limits_the_evaluations(traced: Workspace, recorder: Recorder) -> None:
    thread = await traced.create_thread("Launch")
    online = OnlineEvaluator([judge(recorder)], input=build, budget=Budget(max_evaluations=1))
    kept = Kept(online)
    runner = Runner(make_agent(Script(say("Done."), say("Done."))), app=Gate(), evaluators=[kept])
    await started(await runner.send(traced, thread.id, "Draft")).wait()
    await online.drain()
    await started(await runner.send(traced, thread.id, "Again")).wait()
    first, second = await kept.results()
    assert first.skipped == ()
    assert second.skipped == ("helpful",)
    assert len(await verdicts(traced)) == 1
    assert online.evaluation.budget is not None
    assert online.evaluation.budget.evaluations == 1


async def test_threads_are_judged_for_task_completion(
    traced: Workspace, recorder: Recorder
) -> None:
    thread: Thread = await traced.create_thread("Launch")

    def completed(transcript: Transcript) -> TaskCompletion:
        return TaskCompletion(completed=transcript.result is not None, quality=4, reason="Drafted")

    online = OnlineEvaluator(
        [FunctionEvaluator(completed, verdict_type=TaskCompletion, name="completion")],
        input=completion_transcript,
        on="thread",
    )
    drafting = call("create_artifact", kind="note", data={"text": "Ship Monday"})
    script = Script(drafting, say("Done."))
    kept = Kept(online)
    runner = Runner(make_agent(script), app=Gate(), evaluators=[kept])
    await started(await runner.send(traced, thread.id, "Draft a launch note")).wait()
    [result] = await kept.results()
    assert result.key == thread.id
    [(who, given)] = await verdicts(traced)
    assert who == EvaluatorActor(name="completion", version="1").participant
    assert given.target == ThreadTarget(thread_id=thread.id)
    assert given.value == {"completed": True, "quality": 4, "reason": "Drafted"}
