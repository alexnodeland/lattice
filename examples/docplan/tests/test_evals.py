"""The evaluation loop, offline: people's feedback becomes a dataset, a judge that agrees with it
judges the server's turns and a replay of them, and the measures come from the log."""

import contextlib
import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import Script, call, say, wait_for
from fastapi.testclient import TestClient
from pydantic_ai import ModelMessage, ModelRequest, ModelResponse, ToolReturnPart, UserPromptPart
from rich.console import Console

from artifactr import SystemActor, Workspace, Workspaces
from artifactr.core import EvaluatorActor, FeedbackGiven, TurnTarget
from artifactr.sql import SqlStorage
from docplan import evaluate
from docplan.agent import build_agent
from docplan.app import TENANT, create_app, open_database
from docplan.artifacts import Doc, EditSize, Plan
from docplan.cli import State, command_frame, parse_line
from docplan.evals import (
    Measures,
    TurnEdits,
    calibrate,
    dataset,
    edit_size_judge,
    judge_from_environment,
    measures,
    online_from_environment,
    replay,
)
from evalr import Dataset, Example, measure
from evalr.measures import Turn

BASE = "/v1/workspaces/main"
DRAFT = "We ship search on Friday.\n\nThe index is ready."
MOVED = "We ship search on Monday.\n\nThe index is ready."
REWRITTEN = "Launch plan: docs publish their guide first, then support briefs customers."
OURS = "We ship search on Monday.\n\nThe index is ready. The docs team has the guide."


@dataclass(frozen=True)
class Chat:
    """What the person and the agent did, kept in a database."""

    database_url: str
    doc_id: str
    turns: list[str]
    """The runs of the first thread, in order."""


def post(client: TestClient, frame: dict[str, Any]) -> None:
    result = client.post(f"{BASE}/commands", json=frame).json()
    assert result["ok"], result


def events(client: TestClient, event_type: str) -> list[dict[str, Any]]:
    return [e for e in client.get(f"{BASE}/events").json() if e["event"]["type"] == event_type]


def type_in(client: TestClient, line: str, state: State) -> None:
    """Give feedback as a line typed in the terminal client."""
    frame = parse_line(line, state)
    assert isinstance(frame, dict)
    post(client, frame)


def ask(client: TestClient, thread_id: str, content: str) -> str:
    """Post a message, wait for the agent's turn to end, and return its run."""
    ended = len(events(client, "run_ended"))
    post(client, command_frame(type="post_message", thread_id=thread_id, content=content))
    wait_for(lambda: len(events(client, "run_ended")) > ended)
    return events(client, "run_ended")[-1]["event"]["run_id"]


@pytest.fixture
def chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: Script) -> Chat:
    """Alice and the agent write a launch doc, and the server judges every turn as it ends.

    Alice says what she thinks of each turn's edits, and of the thread, as the terminal
    client's ``/edits`` and ``/done`` do, then rewrites the agent's last version herself. In a
    second thread, she never comes back to the agent's answer.
    """
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'docplan.db'}"
    monkeypatch.setenv("DOCPLAN_DATABASE_URL", database_url)
    monkeypatch.setenv("DOCPLAN_EVAL_SAMPLE_RATE", "1")
    with TestClient(create_app(model=script.model), headers={"x-user": "alice"}) as client:
        post(client, command_frame(type="create_thread", thread_id="t1"))
        script.steps += [
            call("create_artifact", kind="doc", data={"title": "Launch", "text": DRAFT}),
            say("Drafted."),
        ]
        drafted = ask(client, "t1", "Draft a launch doc")
        [doc] = client.get(f"{BASE}/artifacts").json()
        script.steps += [
            call("edit_text", artifact_id=doc["id"], old="Friday", new="Monday"),
            say("Moved."),
            call("edit_text", artifact_id=doc["id"], old=MOVED, new=REWRITTEN),
            say("Rewrote it."),
            say("You're welcome."),
        ]
        turns = [
            drafted,
            ask(client, "t1", "Move it to Monday"),
            ask(client, "t1", "Mention the docs team"),
            ask(client, "t1", "Thanks!"),
        ]
        said = ["/edits ok", "/edits ok", "/edits big all of it", "/edits ok"]
        for turn, line in zip(turns, said, strict=True):
            type_in(client, line, State(thread_id="t1", last_run=turn))
        type_in(client, "/done yes 4 ready to plan", State(thread_id="t1"))
        patch = {"kind": "text_edits", "edits": [{"old": REWRITTEN, "new": OURS}]}
        post(
            client,
            command_frame(type="edit_artifact", artifact_id=doc["id"], base_version=3, patch=patch),
        )

        post(client, command_frame(type="create_thread", thread_id="t2"))
        script.steps += [say("It moves search to Monday.")]
        ask(client, "t2", "Summarize the doc")
        wait_for(lambda: len(events(client, "feedback_given")) == 5 + 5)  # people's and the judge's
    return Chat(database_url, doc["id"], turns)


@contextlib.asynccontextmanager
async def opened(database_url: str, workspace_id: str = "main") -> AsyncIterator[Workspace]:
    """The server's workspace, read from its database as ``docplan-eval`` reads it."""
    engine = open_database(database_url)
    try:
        workspaces = Workspaces(SqlStorage(engine), types=[Doc, Plan])
        yield await workspaces.open(TENANT, workspace_id, actor=SystemActor())
    finally:
        await engine.dispose()


# ─── the loop ─────────────────────────────────────────────────────────────────


async def test_peoples_feedback_is_a_dataset_the_judge_agrees_with(chat: Chat) -> None:
    async with opened(chat.database_url) as workspace:
        examples = await dataset(workspace)
    assert [e.verdict for e in examples] == [
        EditSize(too_big=False),
        EditSize(too_big=False),
        EditSize(too_big=True, comment="all of it"),
        EditSize(too_big=False),
    ]
    assert [e.metadata["given_by"] for e in examples] == ["user:alice"] * 4, "not the judge's"
    drafted, moved, rewritten, thanked = [e.input for e in examples]
    # Each input is the turn as it ended: what was asked, and the doc before and after.
    assert (drafted.request, drafted.before, drafted.reply) == (
        "Draft a launch doc",
        {},
        "Drafted.",
    )
    assert drafted.after == {chat.doc_id: Doc(title="Launch", text=DRAFT)}
    assert moved.history == [
        Turn(role="person", text="Draft a launch doc"),
        Turn(role="agent", text="Drafted."),
    ]
    assert (moved.before[chat.doc_id].text, moved.after[chat.doc_id].text) == (DRAFT, MOVED)
    assert (rewritten.before[chat.doc_id].text, rewritten.after[chat.doc_id].text) == (
        MOVED,
        REWRITTEN,
    )
    assert thanked.before == thanked.after

    measured = await measure(edit_size_judge(), examples)
    assert (measured.agreement.score, measured.agreement.fields["too_big"].kappa) == (1.0, 1.0)


async def test_the_server_judges_its_turns_as_they_end(chat: Chat) -> None:
    async with opened(chat.database_url) as workspace:
        log = await workspace.read()
    judged = {
        e.event.target.run_id: e.event.value["too_big"]
        for e in log
        if isinstance(e.event, FeedbackGiven)
        and isinstance(e.event.target, TurnTarget)
        and e.actor == EvaluatorActor(name="edit-size", version="1:0.5")
    }
    assert [judged[turn] for turn in chat.turns] == [False, False, True, False]
    assert len(judged) == 5, "the second thread's turn too"


async def test_a_replay_judges_the_agent_on_the_same_turns(chat: Chat) -> None:
    def keep_it_small(messages: list[ModelMessage]) -> ModelResponse:
        """A candidate agent that mentions the docs team in one line, and edits nothing else."""
        [*_, request] = messages
        assert isinstance(request, ModelRequest)
        if any(isinstance(part, ToolReturnPart) for part in request.parts):
            return say("Done.")
        prompts = [part.content for part in request.parts if isinstance(part, UserPromptPart)]
        if "Mention the docs team" in prompts:
            ready = "The index is ready."
            return call("edit_text", artifact_id=chat.doc_id, old=ready, new=f"{ready} Docs too.")
        return say(" " if "Thanks!" in prompts else "Noted.")  # no reply to thanks

    async with opened(chat.database_url) as workspace:
        examples = await dataset(workspace)
    candidate = build_agent(Script(*[keep_it_small] * 5).model)
    result = await replay(candidate, examples, edit_size_judge())
    assert [item.errors for item in result.items] == [()] * 4
    assert [v.value for v in result.verdicts("edit-size").values()] == [EditSize(too_big=False)] * 4
    replayed = result.items[2].output
    assert replayed is not None
    assert (replayed.request, replayed.reply) == ("Mention the docs team", "Done.")
    assert replayed.after[chat.doc_id].text == f"{MOVED} Docs too."
    thanked = result.items[3].output
    assert thanked is not None
    assert thanked.reply is None


async def test_the_measures_come_from_the_log(chat: Chat) -> None:
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    async with opened(chat.database_url) as workspace:
        found = await measures(workspace, window=timedelta(hours=1), now=tomorrow)
    # Alice said the thread was done; she left the second thread; she rewrote one of the
    # agent's three versions of the doc.
    assert found == Measures(completion=1.0, drop_off=0.5, rewrites=1 / 3)


# ─── the judge ────────────────────────────────────────────────────────────────


def edited(example_id: str, percent: int, *, too_big: bool) -> Example[TurnEdits, EditSize]:
    """A turn that changed ``percent`` of a doc, and whether people found that too big."""
    kept = "a" * (100 - percent)
    turn = TurnEdits(
        request="Tighten it up",
        before={"doc": Doc(text=kept + "b" * percent)},
        after={"doc": Doc(text=kept + "c" * percent)},
    )
    return Example(id=example_id, input=turn, verdict=EditSize(too_big=too_big))


async def test_calibration_picks_the_threshold_people_agree_with() -> None:
    # People find any change of more than a quarter of the doc too big. turn-5 to turn-7 are
    # held out, by their ids.
    changed = [10, 35, 60, 5, 40, 15, 80, 45]
    examples = Dataset(
        "edits",
        [edited(f"turn-{i}", p, too_big=p > 25) for i, p in enumerate(changed, start=1)],
        input_type=TurnEdits,
        verdict_type=EditSize,
    )
    judge, measured = await calibrate(edit_size_judge(), examples)
    assert (judge.name, judge.version) == ("edit-size", "1:0.25")
    assert (measured.agreement.n, measured.agreement.score) == (3, 1.0)


async def test_too_few_examples_are_measured_without_calibrating() -> None:
    examples = Dataset(
        "edits", [edited("turn-1", 35, too_big=True)], input_type=TurnEdits, verdict_type=EditSize
    )
    judge, measured = await calibrate(edit_size_judge(), examples)
    assert judge.version == "1:0.5"
    assert (measured.agreement.n, measured.agreement.score) == (1, 0.0)


async def test_a_first_draft_is_never_too_big() -> None:
    judge = edit_size_judge(0.0)
    fresh = TurnEdits(request="Draft it", after={"doc": Doc(text="All new.")})
    assert (await judge.evaluate(fresh)).value == EditSize(too_big=False)
    gone = TurnEdits(request="Drop it", before={"doc": Doc(text="Old.")})
    assert (await judge.evaluate(gone)).value == EditSize(too_big=True)


def test_the_judge_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from evalr.dspy import DspyJudge  # the dspy extra's, imported only where it is used

    assert judge_from_environment().version == "1:0.5"
    monkeypatch.setenv("DOCPLAN_JUDGE_THRESHOLD", "0.25")
    assert judge_from_environment().version == "1:0.25"
    monkeypatch.setenv("DOCPLAN_JUDGE_MODEL", "openai/gpt-5-mini")
    judge = judge_from_environment()
    assert isinstance(judge, DspyJudge)
    assert (judge.name, judge.verdict_type) == ("edit-size-judge", EditSize)


def test_online_evaluation_is_off_until_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    assert online_from_environment() is None
    monkeypatch.setenv("DOCPLAN_EVAL_SAMPLE_RATE", "0.1")
    monkeypatch.setenv("DOCPLAN_EVAL_BUDGET", "50")
    online = online_from_environment()
    assert online is not None
    assert online.evaluation.sample_rate == 0.1
    assert online.evaluation.budget is not None
    assert online.evaluation.budget.max_evaluations == 50


# ─── docplan-eval ─────────────────────────────────────────────────────────────


def printed() -> tuple[Console, io.StringIO]:
    out = io.StringIO()
    return Console(file=out, width=200, color_system=None, highlight=False), out


async def test_docplan_eval_runs_each_step(chat: Chat) -> None:
    console, out = printed()
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    for step in ("judge", "measures"):
        await evaluate.run(
            step, database_url=chat.database_url, workspace_id="main", console=console, now=tomorrow
        )
    candidate = Script(*[say("Noted.")] * 4)
    await evaluate.run(
        "replay",
        database_url=chat.database_url,
        workspace_id="main",
        console=console,
        model=candidate.model,
    )
    judged, agreed, measured, replayed = out.getvalue().splitlines()
    assert judged == "4 turns with people's edit_size feedback"
    # Which turns are held out depends on their ids, but every threshold but 0.75 agrees.
    assert agreed.startswith("edit-size@1:0.5 agrees with people 1.00 on ")
    assert measured == "task completion 1.00, drop-off 0.50, rewrite rate 0.33"
    assert replayed == "Replayed 4 turns: edit-size found 0 too big, where people found 1; 0 failed"


def test_docplan_eval_reads_the_database_in_the_environment(
    chat: Chat, capsys: pytest.CaptureFixture[str]
) -> None:
    evaluate.main(["measures", "--workspace", "empty", "--window", "5"])
    assert capsys.readouterr().out == "task completion n/a, drop-off n/a, rewrite rate n/a\n"


def test_docplan_eval_needs_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCPLAN_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="set DOCPLAN_DATABASE_URL"):
        evaluate.main(["judge"])
