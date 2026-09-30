"""The terminal client: parsing and rendering, then whole sessions against a running server."""

import asyncio
import io
import re
import time
from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest
from conftest import Hold, Script, call, say
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from websockets.exceptions import ConnectionClosedError

from docplan import cli
from docplan.cli import Client, Local, Renderer, State, command_frame, parse_line

ALICE = {"kind": "user", "id": "alice", "name": "alice"}
AGENT = {"kind": "agent", "thread_id": "thr_1", "run_id": "run_1", "name": "docplan"}
JUDGE = {"kind": "evaluator", "name": "edit-size", "version": "1:0.5"}


def terminal() -> tuple[Console, io.StringIO]:
    out = io.StringIO()
    return Console(file=out, width=100, color_system=None, highlight=False), out


# ─── parsing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "command"),
    [
        (
            "Plan the launch",
            {"type": "post_message", "thread_id": "thr_1", "content": "Plan the launch"},
        ),
        (
            "/accept prp_1",
            {"type": "respond_to_proposal", "proposal_id": "prp_1", "decision": "accept"},
        ),
        (
            "/reject prp_1  too vague ",
            {
                "type": "respond_to_proposal",
                "proposal_id": "prp_1",
                "decision": "reject",
                "reason": "too vague",
            },
        ),
        (
            "/reject prp_1",
            {
                "type": "respond_to_proposal",
                "proposal_id": "prp_1",
                "decision": "reject",
                "reason": None,
            },
        ),
        ("/mode suggest", {"type": "set_thread_mode", "thread_id": "thr_1", "mode": "suggest"}),
        ("/stop", {"type": "stop_run", "run_id": "run_1"}),
        (
            "/rate 4 good plan",
            {
                "type": "give_feedback",
                "feedback_type": "rating",
                "target": {"kind": "turn", "run_id": "run_0"},
                "value": {"stars": 4, "comment": "good plan"},
            },
        ),
        (
            "/rate 2",
            {
                "type": "give_feedback",
                "feedback_type": "rating",
                "target": {"kind": "turn", "run_id": "run_0"},
                "value": {"stars": 2, "comment": None},
            },
        ),
        (
            "/edits big rewrote my intro",
            {
                "type": "give_feedback",
                "feedback_type": "edit_size",
                "target": {"kind": "turn", "run_id": "run_0"},
                "value": {"too_big": True, "comment": "rewrote my intro"},
            },
        ),
        (
            "/edits ok",
            {
                "type": "give_feedback",
                "feedback_type": "edit_size",
                "target": {"kind": "turn", "run_id": "run_0"},
                "value": {"too_big": False, "comment": None},
            },
        ),
        (
            "/done yes 4  ready to plan",
            {
                "type": "give_feedback",
                "feedback_type": "task_completion",
                "target": {"kind": "thread", "thread_id": "thr_1"},
                "value": {"completed": True, "quality": 4, "reason": "ready to plan"},
            },
        ),
        (
            "/done no 2",
            {
                "type": "give_feedback",
                "feedback_type": "task_completion",
                "target": {"kind": "thread", "thread_id": "thr_1"},
                "value": {"completed": False, "quality": 2, "reason": None},
            },
        ),
    ],
)
def test_lines_become_command_frames(line: str, command: dict[str, Any]) -> None:
    frame = parse_line(line, State("thr_1", active_run="run_1", last_run="run_0"))
    assert isinstance(frame, dict)
    assert (frame["type"], frame["command"]) == ("command", command)
    assert frame["command_id"].startswith("cmd_")


@pytest.mark.parametrize(
    ("line", "action"),
    [
        ("  ", None),
        ("/stop", Local("note", "The agent is not working.")),
        ("/show art_1", Local("show", "art_1")),
        ("/list", Local("list")),
        ("/quit", Local("quit")),
        ("/help", Local("help")),
        ("/accept", Local("help")),
        ("/mode fast", Local("help")),
        ("/dance", Local("help")),
        ("/rate 4", Local("note", "There is no turn to rate yet.")),
        ("/edits ok", Local("note", "There is no turn to rate yet.")),
        ("/done maybe 3", Local("help")),
        ("/done yes 6", Local("help")),
    ],
)
def test_other_lines_are_handled_by_the_client(line: str, action: Local | None) -> None:
    assert parse_line(line, State("thr_1")) == action


def test_a_rating_needs_stars() -> None:
    assert parse_line("/rate great", State("thr_1", last_run="run_1")) == Local("help")
    assert parse_line("/edits huge", State("thr_1", last_run="run_1")) == Local("help")


# ─── rendering ────────────────────────────────────────────────────────────────


def event(actor: dict[str, Any], run: str | None = None, **fields: Any) -> dict[str, Any]:
    """An event frame; ``run`` is the envelope's ``run_id``."""
    return {"type": "event", "seq": 1, "actor": actor, "run_id": run, "event": fields}


def live(delta: str) -> dict[str, Any]:
    return {
        "type": "live",
        "run_id": "run_1",
        "event": {"type": "text_delta", "part": 0, "delta": delta},
    }


FRAMES: list[dict[str, Any]] = [
    {"type": "welcome", "head_seq": 0, "active_runs": []},
    event(ALICE, type="message_posted", content="Plan it"),
    event(AGENT, "run_1", type="run_started", run_id="run_1"),
    {"type": "live", "run_id": "run_1", "event": {"type": "part_started", "part": 0}},
    live("Working "),
    live("hard "),
    event(AGENT, "run_1", type="tool_called", tool_name="add_task", args_summary='{"title": "x"}'),
    event(AGENT, "run_1", type="tool_returned", status="ok", summary="added"),
    event(AGENT, "run_1", type="tool_returned", status="retry", summary="no task t9"),
    live("on it."),
    event(AGENT, "run_1", type="message_posted", content="Working on it."),
    live(" (late)"),
    event(
        AGENT,
        "run_1",
        type="proposal_created",
        proposal_id="prp_1",
        rationale="to track it",
        change={"type": "create_artifact", "kind": "plan"},
    ),
    event(
        AGENT,
        "run_1",
        type="proposal_created",
        proposal_id="prp_2",
        change={"type": "edit_artifact", "artifact_id": "art_1", "summary": "added 'x'"},
    ),
    event(
        AGENT,
        "run_1",
        type="proposal_created",
        proposal_id="prp_3",
        change={"type": "edit_artifact", "artifact_id": "art_1"},
    ),
    event(
        AGENT,
        "run_1",
        type="proposal_created",
        proposal_id="prp_4",
        change={"type": "archive_artifact", "artifact_id": "art_1"},
    ),
    event(
        AGENT,
        "run_1",
        type="run_paused",
        run_id="run_1",
        requests=[
            {"kind": "question", "tool_name": "ask_user", "args": {"question": "Who owns it?"}},
            {"kind": "approval", "tool_name": "delete_everything", "args": {}},
        ],
    ),
    event(ALICE, type="proposal_resolved", proposal_id="prp_1", decision="accept"),
    event(ALICE, type="proposal_resolved", proposal_id="prp_2", decision="reject"),
    event(ALICE, type="artifact_changed", artifact_id="art_1", version=2, summary="added 'x'"),
    event(
        {"kind": "external_agent", "client_id": "mcp"},
        type="artifact_archived",
        artifact_id="art_1",
    ),
    event({"kind": "system"}, type="app_event", name="audit"),
    event(AGENT, "run_2", type="message_posted", content="Done."),
    event(AGENT, "run_2", type="run_ended", status="completed"),
    event(AGENT, "run_3", type="run_ended", status="stopped"),
    event(AGENT, "run_4", type="run_ended", status="failed", error="model timed out"),
    event(ALICE, type="feedback_given", feedback_type="rating", value={"stars": 4}),
    event(ALICE, type="feedback_given", feedback_type="edit_size", value={"too_big": True}),
    event(JUDGE, type="feedback_given", feedback_type="edit_size", value={"too_big": False}),
    event(
        ALICE,
        type="feedback_given",
        feedback_type="task_completion",
        value={"completed": True, "quality": 4},
    ),
    event(
        ALICE,
        type="feedback_given",
        feedback_type="task_completion",
        value={"completed": False, "quality": 2},
    ),
    event(ALICE, type="feedback_given", feedback_type="other", value={}),
    {"type": "command_result", "command_id": "cmd_1", "ok": True},
    {
        "type": "command_result",
        "command_id": "cmd_2",
        "ok": False,
        "rejection": {"message": "nope"},
    },
    {"type": "error", "message": "not a command frame"},
    {"type": "replay_complete", "up_to_seq": 1},
]


def test_frames_render_as_a_transcript() -> None:
    console, out = terminal()
    state = State("thr_1")
    renderer = Renderer(console, state)
    for frame in FRAMES:
        renderer.frame(frame)
    assert out.getvalue().splitlines() == [
        "alice: Plan it",
        "docplan is working…",
        "docplan: Working hard ",
        '  · add_task {"title": "x"}',
        "    ↳ retry: no task t9",
        "docplan: on it.",
        "? docplan proposes to create a plan (to track it)",
        "  /accept prp_1 or /reject prp_1",
        "? docplan proposes to edit art_1: added 'x'",
        "  /accept prp_2 or /reject prp_2",
        "? docplan proposes to edit art_1",
        "  /accept prp_3 or /reject prp_3",
        "? docplan proposes to archive art_1",
        "  /accept prp_4 or /reject prp_4",
        "docplan asks: Who owns it?",
        "  (reply to answer)",
        "docplan wants to call delete_everything",
        "alice accepted prp_1",
        "alice rejected prp_2",
        "✎ alice changed art_1 (v2): added 'x'",
        "✖ mcp archived art_1",
        "docplan: Done.",
        "docplan's run stopped",
        "docplan's run failed: model timed out",
        "alice rated the turn ★★★★☆",
        "alice found the turn's edits too big",
        "edit-size found the turn's edits fine",
        "alice found the thread done, 4/5",
        "alice found the thread not done, 2/5",
        "✗ nope",
        "✗ not a command frame",
    ]
    assert (state.active_run, state.last_run) == (None, "run_1")


# ─── sessions against a running server ────────────────────────────────────────


class Typist:
    """Types each line into the client once the terminal shows what the line waits for."""

    def __init__(self, out: io.StringIO, *steps: tuple[str, str | Callable[[str], str]]) -> None:
        self._out = out
        self._steps = list(steps)

    async def __call__(self) -> str:
        wait, line = self._steps.pop(0)
        deadline = time.monotonic() + 5
        while wait not in self._out.getvalue():
            assert time.monotonic() < deadline, f"never saw {wait!r} in:\n{self._out.getvalue()}"
            await asyncio.sleep(0.01)
        return line(self._out.getvalue()) if callable(line) else line


def found(pattern: str, template: str) -> Callable[[str], str]:
    """A line made from what ``pattern``'s group matched first in the terminal's output."""

    def line(out: str) -> str:
        match = re.search(pattern, out)
        assert match, f"no {pattern!r} in:\n{out}"
        return template.format(match[1])

    return line


DRAFT = [
    call("create_artifact", kind="doc", data={"title": "Launch", "text": "Ship on **Friday**."}),
    call("create_artifact", kind="plan", data={"goal": "Ship search"}),
    say("Drafted."),
]


async def test_an_interactive_session(server: str, script: Script) -> None:
    script.steps += DRAFT
    console, out = terminal()
    typist = Typist(
        out,
        ("/help for commands", ""),
        ("/help for commands", "/help"),
        ("/quit", "/list"),
        ("No artifacts yet.", "/stop"),
        ("The agent is not working.", "Plan the launch"),
        ("docplan: Drafted.", "/list"),
        ("doc v1  Launch", found(r"created doc (art_\w+)", "/show {}")),
        ("Ship on Friday.", "/show art_nope"),
        ("No artifact art_nope.", found(r"/accept (prp_\w+)", "/accept {}")),
        ("accepted", found(r"created plan (art_\w+)", "/show {}")),
        ("Goal: Ship search", "/reject prp_nope too vague"),
        ("✗", "/mode suggest"),
        ("switched the thread to suggest mode", "/quit"),
    )
    await cli.run(url=server, workspace="main", user="alice", console=console, read_line=typist)
    transcript = out.getvalue()
    assert "alice: Plan the launch" in transcript
    assert re.search(r"✚ docplan created doc art_\w+", transcript)
    assert re.search(r"\? docplan proposes to create a plan\n  /accept prp_\w+", transcript)
    assert re.search(r"✚ alice created plan art_\w+", transcript), "accepting creates it"


async def test_a_scripted_session_waits_for_each_reply(server: str, script: Script) -> None:
    script.steps += [*DRAFT, say("Nothing else to do.")]
    console, out = terminal()
    await cli.run(
        url=server,
        workspace="main",
        user="alice",
        send=["Plan the launch", "Anything else?"],
        console=console,
    )
    transcript = out.getvalue()
    assert transcript.index("docplan: Drafted.") < transcript.index("alice: Anything else?")
    assert transcript.rstrip().endswith("docplan: Nothing else to do.")

    console, out = terminal()
    script.steps += [say("Hello again.")]
    await cli.run(url=server, workspace="main", user="bob", send=["Hi"], console=console)
    assert "created doc" not in out.getvalue(), "a new thread does not replay the workspace"


async def test_rejoining_a_thread_replays_it_and_follows_its_run(
    server: str, script: Script
) -> None:
    hold = Hold(say("Released."))
    script.steps += [hold]
    async with httpx.AsyncClient(base_url=server, headers={"x-user": "bob"}) as http:
        for command in (
            {"type": "create_thread", "thread_id": "thr_1"},
            {"type": "post_message", "thread_id": "thr_1", "content": "Go"},
        ):
            await http.post("/v1/workspaces/main/commands", json=command_frame(**command))
    await asyncio.to_thread(hold.entered.wait, 5)

    def release(out: str) -> str:
        hold.released.set()
        return ""

    console, out = terminal()
    typist = Typist(out, ("docplan is working…", release), ("docplan: Released.", "/quit"))
    await cli.run(
        url=server,
        workspace="main",
        user="alice",
        thread="thr_1",
        console=console,
        read_line=typist,
    )
    assert out.getvalue().startswith("bob: Go\ndocplan is working…\n")


async def test_stopping_the_agent(server: str, script: Script) -> None:
    script.steps += [Hold(say("Never said."))]
    console, out = terminal()
    typist = Typist(
        out,
        ("/help for commands", "Go"),
        ("docplan is working…", "/stop"),
        ("docplan's run stopped", "/quit"),
    )
    await cli.run(url=server, workspace="main", user="alice", console=console, read_line=typist)


class Dropped:
    """A connection that ends as soon as it is read, cleanly or not."""

    def __init__(self, ending: BaseException) -> None:
        self._ending = ending

    async def send(self, text: str) -> None:
        pass

    def __aiter__(self) -> "Dropped":
        return self

    async def __anext__(self) -> str:
        raise self._ending


@pytest.mark.parametrize("ending", [StopAsyncIteration(), ConnectionClosedError(None, None)])
async def test_a_script_stops_when_the_connection_ends(ending: BaseException) -> None:
    console, _ = terminal()
    client = Client(cast(Any, Dropped(ending)), cast(Any, None), State("thr_1"), console)
    receiver = asyncio.create_task(client.receive())
    with pytest.raises(ConnectionError, match="the server closed the connection"):
        await client.script(["Hi"])
    await receiver


def test_main_posts_and_exits(
    server: str, script: Script, capsys: pytest.CaptureFixture[str]
) -> None:
    script.steps += [say("Hello, Carol.")]
    cli.main(["--url", server, "--user", "carol", "--send", "Hi"])
    assert "docplan: Hello, Carol." in capsys.readouterr().out


def test_main_explains_a_connection_failure() -> None:
    with pytest.raises(SystemExit, match=r"docplan: cannot talk to http://127\.0\.0\.1:9: "):
        cli.main(["--url", "http://127.0.0.1:9"])


async def test_the_terminal_prompt_reads_lines_and_quits_at_the_end() -> None:
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        read_line = cli.terminal_prompt()
        pipe.send_text("hello\r")
        assert await read_line() == "hello"
        pipe.send_text("\x04")  # Ctrl-D
        assert await read_line() == "/quit"
