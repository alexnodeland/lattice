"""Experiment tasks: a thread's turn replayed against a candidate agent, in isolation."""

from evalr.core import Dataset, Example, FunctionEvaluator
from evalr.measures import Turn
from evalr.memory import InMemoryExperimentTracker
from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolReturnPart

from artifactr.evals import Replay, Seed, replay_task
from tests.agent.conftest import Gate, Script, call, make_agent, say
from tests.artifact_types import Checklist, Helpfulness, Note


class Request(BaseModel):
    """An example's input: the thread before the turn, and the message that started it."""

    before: list[Turn]
    request: str
    note: str


class Outcome(BaseModel):
    """What the experiment's evaluator judges."""

    reply: str | None
    notes: list[str]
    proposals: int


def edit_then_answer(messages: list[ModelMessage]) -> ModelResponse:
    """A candidate that edits the note once, then says it is done."""
    last = messages[-1]
    if isinstance(last, ModelRequest) and any(isinstance(p, ToolReturnPart) for p in last.parts):
        return say("Done.")
    return call("edit_text", artifact_id="note_1", old="Monday", new="Tuesday")


def seed(example: Example[Request, Helpfulness]) -> Seed:
    return Seed(
        prompt=example.input.request,
        messages=example.input.before,
        artifacts={"note_1": Note(text=example.input.note)},
        title="Launch",
    )


def outcome(replay: Replay) -> Outcome:
    notes = [str(revision.data["text"]) for revision in replay.revisions]
    proposals = sum(1 for e in replay.events if e.event.type == "proposal_created")
    return Outcome(reply=replay.message, notes=notes, proposals=proposals)


def rated(done: Outcome) -> Helpfulness:
    return Helpfulness(rating=5 if done.notes else 1)


def example(i: int) -> Example[Request, Helpfulness]:
    return Example(
        id=f"e{i}",
        input=Request(
            before=[
                Turn(role="person", text="Draft a launch note"),
                Turn(role="agent", text="Drafted."),
                Turn(role="system", text="Alice joined."),
            ],
            request="Move it to Tuesday",
            note=f"Ship Monday, take {i}",
        ),
        verdict=Helpfulness(rating=4),
    )


async def test_a_candidate_replays_each_example_in_isolation() -> None:
    script = Script(*[edit_then_answer] * 4)
    task = replay_task(
        make_agent(script), app=Gate(), seed=seed, output=outcome, types=[Note, Checklist]
    )
    dataset = Dataset(
        "moves", [example(1), example(2)], input_type=Request, verdict_type=Helpfulness
    )
    judge = FunctionEvaluator(rated, verdict_type=Helpfulness, name="rated")
    result = await InMemoryExperimentTracker().run_experiment(
        "tuesday", dataset=dataset, task=task, evaluators=[judge]
    )
    assert [item.errors for item in result.items] == [(), ()]
    assert [item.output for item in result.items] == [
        Outcome(reply="Done.", notes=[f"Ship Tuesday, take {i}"], proposals=0) for i in (1, 2)
    ]
    assert [v.value for v in result.verdicts("rated").values()] == [Helpfulness(rating=5)] * 2
    # The candidate saw the thread as it was: its messages as history and the note it followed,
    # with no change notes about the seeding among its prompts.
    first = script.requests[0]
    assert [type(message) for message in first] == [ModelRequest, ModelResponse, ModelRequest]
    assert [p.content for p in first[1].parts if isinstance(p, TextPart)] == ["Drafted."]
    assert script.prompt_texts(0) == ["Draft a launch note", "Alice joined.", "Move it to Tuesday"]
    assert "Ship Monday, take" in script.instructions(0)


async def test_a_replay_in_suggest_mode_proposes() -> None:
    async def proposed(replay: Replay) -> Outcome:
        [thread] = await replay.workspace.threads()
        assert thread.mode == "suggest"
        return outcome(replay)

    def suggesting(example: Example[Request, Helpfulness]) -> Seed:
        return Seed(prompt="Move it", artifacts={"note_1": Note(text="Monday")}, mode="suggest")

    script = Script(*[edit_then_answer] * 2)
    task = replay_task(make_agent(script), app=Gate(), seed=suggesting, output=proposed)
    done = await task(example(1))
    assert done == Outcome(reply="Done.", notes=[], proposals=1)


async def test_a_turn_that_ends_without_a_reply_has_no_message() -> None:
    task = replay_task(
        make_agent(Script(say("  "))),
        app=Gate(),
        seed=lambda e: Seed(prompt="Hello"),
        output=outcome,
    )
    assert await task(example(1)) == Outcome(reply=None, notes=[], proposals=0)
