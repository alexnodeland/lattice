"""A terminal client for docplan that speaks the thread protocol over WebSocket.

Interactive::

    docplan --user alice

Scripted: post each message, print what happens until the agent finishes, then exit::

    docplan --user alice --send "Draft a launch doc" --send "Now plan it"

The parsing and rendering are plain functions over protocol frames (JSON objects), so a client
in any language follows the same shape: send ``hello``, render the replay, then send command
frames and render event and live frames as they arrive.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.typing import Subprotocol

from artifactr import new_id
from artifactr.core import PROTOCOL
from docplan.artifacts import Doc, Plan

type Frame = dict[str, Any]
"""A protocol frame as JSON."""

HELP = """\
Type a message to talk to the agent. Commands:
  /list                 list the workspace's artifacts
  /show ID              show an artifact
  /accept ID            accept a proposal
  /reject ID [REASON]   reject a proposal
  /mode edit|suggest    let the agent edit, or make every change a proposal
  /rate 1-5 [COMMENT]   rate the agent's last turn
  /stop                 stop the agent
  /quit                 leave"""

VIEWS = {"doc": Doc, "plan": Plan}
"""How ``/show`` renders each artifact kind."""


@dataclass(frozen=True)
class Local:
    """Something the client does itself instead of sending it to the server.

    ``name`` is ``quit``, ``list``, ``show`` (``argument`` is the artifact), ``help``, or
    ``note`` (print ``argument``).
    """

    name: str
    argument: str = ""


@dataclass
class State:
    """What the client knows about its thread."""

    thread_id: str
    active_run: str | None = None
    last_run: str | None = None
    """The agent's latest run in the thread, which ``/rate`` rates."""


def parse_line(line: str, state: State) -> Frame | Local | None:
    """Turn a line of input into a command frame, a local action, or nothing."""
    text = line.strip()
    if not text:
        return None
    if not text.startswith("/"):
        return command_frame(type="post_message", thread_id=state.thread_id, content=text)
    name, _, rest = text[1:].partition(" ")
    rest = rest.strip()
    match name:
        case "accept" if rest:
            return command_frame(type="respond_to_proposal", proposal_id=rest, decision="accept")
        case "reject" if rest:
            proposal_id, _, reason = rest.partition(" ")
            return command_frame(
                type="respond_to_proposal",
                proposal_id=proposal_id,
                decision="reject",
                reason=reason.strip() or None,
            )
        case "mode" if rest in ("edit", "suggest"):
            return command_frame(type="set_thread_mode", thread_id=state.thread_id, mode=rest)
        case "rate" if state.last_run and rest[:1] in ("1", "2", "3", "4", "5"):
            stars, _, comment = rest.partition(" ")
            return command_frame(
                type="give_feedback",
                feedback_type="rating",
                target={"kind": "turn", "run_id": state.last_run},
                value={"stars": int(stars), "comment": comment.strip() or None},
            )
        case "rate" if state.last_run is None:
            return Local("note", "There is no turn to rate yet.")
        case "stop" if state.active_run:
            return command_frame(type="stop_run", run_id=state.active_run)
        case "stop":
            return Local("note", "The agent is not working.")
        case "show" if rest:
            return Local("show", rest)
        case "list" | "quit":
            return Local(name)
        case _:
            return Local("help")


def command_frame(**command: Any) -> Frame:
    """Wrap a command in a frame with a fresh ``command_id``."""
    return {"type": "command", "command_id": new_id("cmd"), "command": command}


class Renderer:
    """Prints server frames: messages, streamed replies, artifact changes, proposals and runs."""

    def __init__(self, console: Console, state: State) -> None:
        self._console = console
        self._state = state
        self._agents: dict[str, str] = {}
        """The agent's name in each run, from ``run_started``."""
        self._streamed: set[str] = set()
        """Runs whose reply was printed as it streamed."""
        self._posted: set[str] = set()
        """Runs whose reply is posted. Live and durable frames travel separately, so a run's
        last live frames can arrive after its message; they are ignored."""
        self._streaming = False

    def frame(self, frame: Frame) -> None:
        """Print one server frame. Frames it does not show are ignored."""
        match frame["type"]:
            case "event":
                self._event(frame["event"], frame["actor"], frame.get("run_id"))
            case "live" if frame["event"]["type"] == "text_delta":
                self._delta(frame["run_id"], frame["event"]["delta"])
            case "command_result" if not frame["ok"]:
                self._line(f"[red]✗ {escape(frame['rejection']['message'])}[/]")
            case "error":
                self._line(f"[red]✗ {escape(frame['message'])}[/]")
            case _:
                pass

    def _event(self, event: Frame, actor: Frame, run_id: str | None) -> None:
        who = escape(actor.get("name") or actor.get("id") or actor.get("client_id") or "someone")
        match event["type"]:
            case "message_posted":
                self._message(who, event["content"], run_id)
            case "thread_mode_changed":
                self._line(f"[dim]{who} switched the thread to {event['mode']} mode[/]")
            case "artifact_created":
                self._line(f"[cyan]✚ {who} created {event['kind']} {event['artifact_id']}[/]")
            case "artifact_changed":
                self._line(
                    f"[cyan]✎ {who} changed {event['artifact_id']} (v{event['version']}): "
                    f"{escape(event['summary'])}[/]"
                )
            case "artifact_archived":
                self._line(f"[cyan]✖ {who} archived {event['artifact_id']}[/]")
            case "proposal_created":
                proposal = event["proposal_id"]
                self._line(
                    f"[yellow]? {who} proposes to {describe_change(event['change'])}"
                    + (f" ({escape(event['rationale'])})" if event.get("rationale") else "")
                    + f"\n  /accept {proposal} or /reject {proposal}[/]"
                )
            case "proposal_resolved":
                verdict = "accepted" if event["decision"] == "accept" else "rejected"
                self._line(f"[yellow]{who} {verdict} {event['proposal_id']}[/]")
            case "run_started":
                self._state.active_run = self._state.last_run = event["run_id"]
                self._agents[event["run_id"]] = who
                self._line(f"[dim]{who} is working…[/]")
            case "tool_called":
                self._line(f"[dim]  · {event['tool_name']} {escape(event['args_summary'])}[/]")
            case "tool_returned" if event["status"] != "ok":
                self._line(f"[dim]    ↳ {event['status']}: {escape(event['summary'])}[/]")
            case "run_paused":
                self._state.active_run = None
                for request in event["requests"]:
                    if request["kind"] == "question":
                        question = escape(str(request["args"].get("question", "")))
                        self._line(f"[magenta]{who} asks: {question}\n  (reply to answer)[/]")
                    else:
                        self._line(f"[magenta]{who} wants to call {request['tool_name']}[/]")
            case "feedback_given" if event["feedback_type"] == "rating":
                stars = event["value"]["stars"]
                self._line(f"[dim]{who} rated the turn {'★' * stars}{'☆' * (5 - stars)}[/]")
            case "run_ended":
                self._state.active_run = None
                if event["status"] != "completed":
                    detail = f": {escape(event['error'])}" if event.get("error") else ""
                    self._line(f"[red]{who}'s run {event['status']}{detail}[/]")
            case _:
                pass

    def _message(self, who: str, content: str, run_id: str | None) -> None:
        if run_id is None:  # a person's message
            self._line(f"[bold]{who}[/]: {escape(content)}")
            return
        self._posted.add(run_id)
        if run_id in self._streamed:
            self._end_stream()
        else:
            self._line(f"[green bold]{who}[/]: {escape(content)}")

    def _delta(self, run_id: str, delta: str) -> None:
        if run_id in self._posted:
            return
        if not self._streaming:
            self._console.print(f"[green bold]{self._agents.get(run_id, 'agent')}[/]: ", end="")
            self._streaming = True
            self._streamed.add(run_id)
        self._console.print(delta, end="", markup=False, highlight=False)

    def _end_stream(self) -> None:
        if self._streaming:
            self._console.print()
            self._streaming = False

    def _line(self, markup: str) -> None:
        self._end_stream()
        self._console.print(markup, highlight=False)


def describe_change(change: Frame) -> str:
    """Describe a proposed change in a few words."""
    match change["type"]:
        case "create_artifact":
            return f"create a {change['kind']}"
        case "edit_artifact":
            summary = change.get("summary")
            return f"edit {change['artifact_id']}" + (f": {escape(summary)}" if summary else "")
        case _:
            return f"archive {change['artifact_id']}"


def settles(frame: Frame) -> bool:
    """Whether a scripted client has seen the outcome of what it last sent."""
    match frame:
        case {"type": "event", "event": {"type": "run_ended" | "run_paused"}}:
            return True
        case {"type": "command_result", "ok": False} | {"type": "error"}:
            return True
        case _:
            return False


class Client:
    """A connection to one workspace, following one thread."""

    def __init__(
        self, socket: ClientConnection, http: httpx.AsyncClient, state: State, console: Console
    ) -> None:
        self.socket = socket
        self.http = http
        self.state = state
        self.console = console
        self.renderer = Renderer(console, state)
        self.settled = asyncio.Event()
        self.closed = False

    async def join(self, *, new_thread: bool) -> None:
        """Say hello, then create the thread, or render the replay of the thread rejoined.

        The server sends the live output of the thread's runs, including one already running,
        without being asked.
        """
        await self.send({"type": "hello", "protocol": PROTOCOL, "threads": [self.state.thread_id]})
        await self.socket.recv()  # welcome
        while (frame := json.loads(await self.socket.recv()))["type"] != "replay_complete":
            if not new_thread:
                self.renderer.frame(frame)
        if new_thread:
            await self.send(command_frame(type="create_thread", thread_id=self.state.thread_id))

    async def receive(self) -> None:
        """Render frames until the connection closes."""
        try:
            async for raw in self.socket:
                frame = json.loads(raw)
                self.renderer.frame(frame)
                if settles(frame):
                    self.settled.set()
        except ConnectionClosed:
            pass
        finally:
            self.closed = True
            self.settled.set()

    async def script(self, messages: list[str]) -> None:
        """Post each message and wait until the agent finishes with it."""
        for message in messages:
            self.settled.clear()
            await self.send(
                command_frame(type="post_message", thread_id=self.state.thread_id, content=message)
            )
            await self.settled.wait()
            if self.closed:
                raise ConnectionError("the server closed the connection")

    async def interact(self, read_line: Callable[[], Awaitable[str]]) -> None:
        """Read lines and act on them until ``/quit``."""
        while True:
            match parse_line(await read_line(), self.state):
                case None:
                    pass
                case Local(name="quit"):
                    return
                case Local(name="list"):
                    await self.list_artifacts()
                case Local(name="show", argument=artifact_id):
                    await self.show(artifact_id)
                case Local(name="note", argument=note):
                    self.console.print(f"[dim]{note}[/]")
                case Local():
                    self.console.print(HELP, markup=False)
                case frame:
                    await self.send(frame)

    async def list_artifacts(self) -> None:
        """Print the workspace's artifacts."""
        artifacts = (await self.http.get("/artifacts")).json()
        if not artifacts:
            self.console.print("[dim]No artifacts yet.[/]")
        for artifact in artifacts:
            data = artifact["data"]
            name = data.get("title") or data.get("goal") or ""
            self.console.print(
                f"  {artifact['id']}  {artifact['kind']} v{artifact['version']}  {escape(name)}"
            )

    async def show(self, artifact_id: str) -> None:
        """Print an artifact the way the agent sees it."""
        response = await self.http.get(f"/artifacts/{artifact_id}")
        if response.status_code == HTTPStatus.NOT_FOUND:
            self.console.print(f"[red]No artifact {escape(artifact_id)}.[/]")
            return
        artifact = response.json()
        view = VIEWS[artifact["kind"]].model_validate(artifact["data"])
        self.console.print(f"[dim]{artifact['id']} · {artifact['kind']} v{artifact['version']}[/]")
        self.console.print(Markdown(view.render_for_agent()))

    async def send(self, frame: Frame) -> None:
        """Send one frame."""
        await self.socket.send(json.dumps(frame))


async def run(
    *,
    url: str,
    workspace: str,
    user: str,
    thread: str | None = None,
    send: list[str] | None = None,
    console: Console,
    read_line: Callable[[], Awaitable[str]] | None = None,
) -> None:
    """Connect to a docplan server, then post scripted messages or read lines until ``/quit``.

    Args:
        url: The server's base URL, ``http://`` or ``https://``.
        workspace: The workspace to join.
        user: Who to connect as (the demo server trusts it).
        thread: A thread to rejoin. Omitted, the client starts a new thread.
        send: Messages to post one after another, waiting for the agent after each.
        console: Where to print.
        read_line: Where interactive input comes from. Defaults to a prompt on the terminal.
    """
    base = f"{url.rstrip('/')}/v1/workspaces/{workspace}"
    headers = {"x-user": user}
    state = State(thread_id=thread or new_id("thr"))
    async with (
        connect(
            base.replace("http", "ws", 1) + "/stream",
            subprotocols=[Subprotocol(PROTOCOL)],
            additional_headers=headers,
        ) as socket,
        httpx.AsyncClient(base_url=base, headers=headers) as http,
    ):
        client = Client(socket, http, state, console)
        await client.join(new_thread=thread is None)
        console.print(
            f"[dim]{user} in {workspace}, thread {state.thread_id}. /help for commands.[/]"
        )
        receiver = asyncio.create_task(client.receive())
        try:
            if send:
                await client.script(send)
            else:
                await client.interact(read_line or terminal_prompt())
        finally:
            receiver.cancel()


def terminal_prompt() -> Callable[[], Awaitable[str]]:
    """Read lines from the terminal, keeping output printed while typing above the prompt."""
    session: PromptSession[str] = PromptSession()

    async def read_line() -> str:
        with patch_stdout():
            try:
                return await session.prompt_async("> ")
            except (EOFError, KeyboardInterrupt):
                return "/quit"

    return read_line


def main(argv: list[str] | None = None) -> None:
    """Run the terminal client."""
    parser = argparse.ArgumentParser(prog="docplan", description="Talk to a docplan server.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="the server's base URL")
    parser.add_argument("--workspace", default="main", help="the workspace to join")
    parser.add_argument("--user", default="guest", help="who you are (demo authentication)")
    parser.add_argument("--thread", help="a thread to rejoin; a new thread by default")
    parser.add_argument(
        "--send", action="append", metavar="MESSAGE", help="post a message and wait (repeatable)"
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(
            run(
                url=args.url,
                workspace=args.workspace,
                user=args.user,
                thread=args.thread,
                send=args.send,
                console=Console(),
            )
        )
    except (OSError, WebSocketException) as error:
        sys.exit(f"docplan: cannot talk to {args.url}: {error}")
