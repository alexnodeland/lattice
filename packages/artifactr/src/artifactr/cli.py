#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click",
#     "httpx",
#     "prompt-toolkit",
#     "rich",
#     "websockets",
# ]
# ///
"""
Rich WebSocket Client for the Daydreamed application.

Connects to backend WebSocket and provides a beautiful CLI interface.
"""

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import click
import httpx
import websockets
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.traceback import install

# Install rich traceback handler
install(show_locals=True, width=100, suppress=[click, websockets])

# Theme configuration
DAYDREAM_THEME = Theme(
    {
        "info": "dim cyan",
        "warning": "magenta",
        "danger": "bold red",
        "success": "bold green",
        "command": "bold yellow",
        "time": "dim white",
        "user": "yellow",
        "ai": "green",
        "system": "blue",
        "highlight": "bold cyan",
        "title": "bold blue",
        "thread_id": "bold magenta",
        "command.help": "green",
        "command.exit": "red",
        "command.save": "cyan",
        "command.clear": "yellow",
        "command.history": "blue",
        "command.thread": "magenta",
    }
)

# Set up Rich console with theme
console = Console(theme=DAYDREAM_THEME, highlight=True, record=True)
error_console = Console(stderr=True, style="bold red", theme=DAYDREAM_THEME)

# Message history
message_history: list[dict] = []

# Color scheme for different message types
MESSAGE_COLORS = {
    "system": "system",
    "error": "danger",
    "done": "success",
    "user": "user",
    "thread_created": "warning",
    "unknown": "dim white",
}

# Command prefix
CMD_PREFIX = "/"
COMMANDS = [
    "help",
    "exit",
    "quit",
    "save",
    "export",
    "clear",
    "history",
    "theme",
    "thread",
    "status",
    "version",
    "reconnect",
]
SPINNERS = [
    "dots",
    "point",
    "star",
    "clock",
    "earth",
    "moon",
    "runner",
    "monkey",
    "hearts",
]
DEFAULT_SPINNER = "dots"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8000
DEFAULT_PROTOCOL: Literal["ws", "sse"] = "ws"


def format_timestamp(timestamp: float) -> Text:
    """Format a timestamp into a styled Rich Text object."""
    dt = datetime.fromtimestamp(timestamp)
    return Text(dt.strftime("%H:%M:%S"), style="time")


def display_message(message: dict, full_width: bool = True) -> Panel:
    """Display a message with appropriate styling based on its type and return the Panel."""
    msg_type = message.get("type", "unknown")
    content = message.get("content", "")
    timestamp = message.get("timestamp", datetime.now().timestamp())
    metadata = message.get("metadata", {})

    time_str = format_timestamp(timestamp)

    if msg_type == "system":
        # System messages are blue
        if isinstance(content, str):
            content_renderable = Text(content, style="system")
        else:
            content_renderable = content

        panel = Panel(
            content_renderable,
            border_style="system",
            title=f"[{time_str}] System Message",
            subtitle=metadata.get("source", ""),
            box=box.ROUNDED,
            expand=full_width,
            padding=(1, 2),
        )

    elif msg_type == "error":
        # Error messages are red
        panel = Panel(
            Text(content, style="danger"),
            border_style="danger",
            title=f"[{time_str}] Error",
            subtitle=metadata.get("code", ""),
            box=box.HEAVY,
            expand=full_width,
            padding=(1, 2),
        )

    elif msg_type == "done":
        # Just create a simple panel for done messages
        panel = Panel(
            Text("✓ Completed", style="success"),
            border_style="success",
            title=f"[{time_str}] Done",
            box=box.ROUNDED,
            expand=False,
            padding=(0, 1),
        )

    elif msg_type == "thread_created":
        thread_id = message.get("thread_id")
        panel = Panel(
            Text(
                f"New conversation thread created with ID: {thread_id}",
                style="thread_id",
            ),
            border_style="warning",
            title=f"[{time_str}] Thread Created",
            box=box.ROUNDED,
            expand=full_width,
            padding=(1, 2),
        )

    elif msg_type == "user":
        # Display user message with yellow styling
        if content.startswith(CMD_PREFIX):
            renderable = Text(content, style="command")
        else:
            renderable = Text(content, style="user")

        panel = Panel(
            renderable,
            border_style="user",
            title=f"[{time_str}] You",
            subtitle=metadata.get("session", ""),
            box=box.ROUNDED,
            expand=full_width,
            padding=(1, 2),
        )

    else:
        # Try to detect and render code blocks in markdown
        try:
            # Check for code blocks in the content
            code_blocks = re.findall(r"```(\w+)?\n(.*?)```", content, re.DOTALL)

            if code_blocks:
                # If there are code blocks, we'll handle them specially
                rendered_content = []
                remaining_content = content

                for lang, code in code_blocks:
                    # Split at the code block
                    parts = remaining_content.split(f"```{lang}\n{code}```", 1)

                    # Add the text before the code block if it's not empty
                    if parts[0].strip():
                        rendered_content.append(Markdown(parts[0].strip()))

                    # Add the code block with syntax highlighting
                    language = lang if lang else "python"
                    rendered_content.append(
                        Syntax(
                            code.strip(),
                            language,
                            theme="monokai",
                            line_numbers=True,
                            word_wrap=True,
                        )
                    )

                    # Update remaining content
                    if len(parts) > 1:
                        remaining_content = parts[1]
                    else:
                        remaining_content = ""

                # Add any remaining content
                if remaining_content.strip():
                    rendered_content.append(Markdown(remaining_content.strip()))

                # Create a panel with multiple renderables
                panel = Panel(
                    Columns(rendered_content, expand=True),
                    border_style=MESSAGE_COLORS.get(msg_type, "white"),
                    title=f"[{time_str}] Response",
                    box=box.ROUNDED,
                    expand=full_width,
                    padding=(1, 2),
                )
            else:
                # No code blocks, just use Markdown
                md = Markdown(content)
                panel = Panel(
                    md,
                    border_style=MESSAGE_COLORS.get(msg_type, "white"),
                    title=f"[{time_str}] Response",
                    box=box.ROUNDED,
                    expand=full_width,
                    padding=(1, 2),
                )
        except Exception as e:
            # Fallback to plain text if markdown parsing fails
            panel = Panel(
                Text(f"{content}\n\n[dim](Markdown rendering failed: {e})[/dim]"),
                border_style=MESSAGE_COLORS.get(msg_type, "white"),
                title=f"[{time_str}] {msg_type.title()}",
                box=box.ROUNDED,
                expand=full_width,
                padding=(1, 2),
            )

    # Add to history if not already there
    if message not in message_history:
        message_history.append(message)

    return panel


def save_conversation(
    thread_id: int | None = None, format_type: str = "markdown"
) -> str:
    """Save the conversation history to a file."""
    if not message_history:
        return "No messages to save."

    # Create conversations directory if it doesn't exist
    save_dir = Path("conversations")
    save_dir.mkdir(exist_ok=True)

    # Create filename with thread ID, date, and time
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    thread_part = f"thread_{thread_id}_" if thread_id else ""
    filename = save_dir / f"{thread_part}conversation_{timestamp}.{format_type}"

    with open(filename, "w", encoding="utf-8") as f:
        if format_type == "markdown":
            f.write(
                f"# Conversation {thread_part}at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )
            for msg in message_history:
                msg_type = msg.get("type", "unknown")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", datetime.now().timestamp())
                time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

                if msg_type == "user":
                    f.write(f"## You ({time_str})\n\n{content}\n\n")
                elif msg_type == "system":
                    f.write(f"## System ({time_str})\n\n{content}\n\n")
                elif msg_type == "thread_created":
                    thread_id = msg.get("thread_id")
                    f.write(
                        f"## Thread Created ({time_str})\n\nThread ID: {thread_id}\n\n"
                    )
                elif msg_type == "done":
                    f.write("---\n\n")
                elif msg_type not in ("error", "unknown"):
                    f.write(f"## Response ({time_str})\n\n{content}\n\n")

        elif format_type == "json":
            import json

            json.dump(message_history, f, indent=2)

        elif format_type == "txt":
            f.write(
                f"Conversation {thread_part}at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )
            for msg in message_history:
                msg_type = msg.get("type", "unknown")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", datetime.now().timestamp())
                time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

                if msg_type == "user":
                    f.write(f"[{time_str}] You: {content}\n\n")
                elif msg_type == "system":
                    f.write(f"[{time_str}] System: {content}\n\n")
                elif msg_type == "thread_created":
                    thread_id = msg.get("thread_id")
                    f.write(f"[{time_str}] Thread Created: {thread_id}\n\n")
                elif msg_type == "done":
                    f.write("---\n\n")
                elif msg_type not in ("error", "unknown"):
                    f.write(f"[{time_str}] Response: {content}\n\n")

    return str(filename.absolute())


async def handle_command(
    cmd: str, thread_id: int | None = None, connection=None, protocol: str = "ws"
) -> tuple[bool, str]:
    """Handle special commands prefixed with /."""
    cmd = cmd.strip()
    if not cmd.startswith(CMD_PREFIX):
        return False, ""

    cmd_parts = cmd[1:].split()
    cmd_name = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []

    if cmd_name in ("quit", "exit"):
        if connection:
            if protocol == "ws" and hasattr(connection, "close"):
                await connection.close()
            elif protocol == "sse" and hasattr(connection, "aclose"):
                await connection.aclose()
        return True, "exit"

    elif cmd_name == "help":
        help_table = Table(title="Available Commands", box=box.ROUNDED)
        help_table.add_column("Command", style="command")
        help_table.add_column("Description", style="info")
        help_table.add_column("Usage", style="dim")

        help_table.add_row("/help", "Show this help message", "/help")
        help_table.add_row("/exit, /quit", "Exit the application", "/exit")
        help_table.add_row(
            "/save, /export", "Save conversation to file", "/save [markdown|json|txt]"
        )
        help_table.add_row("/clear", "Clear the screen", "/clear")
        help_table.add_row("/history", "Show message history", "/history [count]")
        help_table.add_row("/thread", "Show current thread ID", "/thread")
        help_table.add_row("/status", "Show connection status", "/status")
        help_table.add_row(
            "/spinner", "Change spinner animation", f"/spinner [{', '.join(SPINNERS)}]"
        )

        console.print(help_table)
        return True, "help"

    elif cmd_name in ("save", "export"):
        format_type = (
            args[0] if args and args[0] in ("markdown", "json", "txt") else "markdown"
        )
        filename = save_conversation(thread_id, format_type)
        console.print(f"[success]Conversation saved to: {filename}[/success]")
        return True, "save"

    elif cmd_name == "clear":
        console.clear()
        return True, "clear"

    elif cmd_name == "history":
        count = int(args[0]) if args and args[0].isdigit() else 5
        count = min(count, len(message_history))

        if count <= 0:
            console.print("[warning]No messages in history[/warning]")
        else:
            console.print(f"[info]Last {count} messages:[/info]")
            for i, msg in enumerate(message_history[-count:]):
                panel = display_message(msg)
                console.print(panel)

        return True, "history"

    elif cmd_name == "thread":
        if thread_id:
            console.print(
                f"[info]Current thread ID: [thread_id]{thread_id}[/thread_id][/info]"
            )
        else:
            console.print("[warning]No active thread[/warning]")
        return True, "thread"

    elif cmd_name == "status":
        conn_status = False
        try:
            if protocol == "ws" and connection:
                # For websockets library, check if connection exists and is open
                # The connection object might not have a 'closed' attribute depending on version
                if hasattr(connection, "closed"):
                    conn_status = not connection.closed
                elif hasattr(connection, "state"):
                    # websockets 10+ uses state property
                    from websockets.protocol import State

                    conn_status = connection.state == State.OPEN
                else:
                    # If we have a connection object, assume it's open
                    conn_status = True
            elif protocol == "sse" and connection:
                if hasattr(connection, "is_closed"):
                    conn_status = not connection.is_closed
                else:
                    # For httpx client, assume it's open if it exists
                    conn_status = True
        except Exception:
            conn_status = False

        if conn_status:
            console.print(
                f"[success]Connected to server using {protocol.upper()}[/success]"
            )
        else:
            console.print(f"[danger]Not connected via {protocol.upper()}[/danger]")
        return True, "status"

    elif cmd_name == "spinner":
        if args and args[0] in SPINNERS:
            console.print(f"[success]Spinner set to: {args[0]}[/success]")
            return True, f"spinner:{args[0]}"
        else:
            spinner_table = Table(title="Available Spinners")
            spinner_table.add_column("Name")
            for spinner in SPINNERS:
                spinner_table.add_row(spinner)
            console.print(spinner_table)
            return True, "spinner_list"

    console.print(
        f"[danger]Unknown command: {cmd_name}[/danger]. Type /help for available commands."
    )
    return True, "unknown"


class DaydreamedCompleter(Completer):
    """Custom completer for command suggestions."""

    def __init__(self, commands: list[str], message_history: list[dict]):
        self.commands = commands
        self.message_history = message_history
        # Extract previous user messages for suggestions
        self.user_messages = [
            msg["content"]
            for msg in self.message_history
            if msg.get("type") == "user" and not msg["content"].startswith(CMD_PREFIX)
        ]

    def get_completions(self, document, complete_event):
        """Get completions for the command."""
        text = document.text

        # Command completion
        if text.startswith(CMD_PREFIX):
            cmd_prefix = text[1:]
            for command in self.commands:
                if command.startswith(cmd_prefix):
                    yield Completion(
                        f"{CMD_PREFIX}{command}",
                        start_position=-len(text),
                        style="bg:#008800 #ffffff",
                        selected_style="bg:#00aa00 #ffffff",
                    )

            # Subcommand completions for specific commands
            if " " in text:
                cmd, arg_prefix = text.split(" ", 1)
                cmd = cmd[1:]  # Remove the / prefix

                if cmd == "save" or cmd == "export":
                    for fmt in ["markdown", "json", "txt"]:
                        if fmt.startswith(arg_prefix):
                            yield Completion(
                                fmt,
                                start_position=-len(arg_prefix),
                                style="bg:#000088 #ffffff",
                                selected_style="bg:#0000aa #ffffff",
                            )

                elif cmd == "spinner":
                    for spinner in SPINNERS:
                        if spinner.startswith(arg_prefix):
                            yield Completion(
                                spinner,
                                start_position=-len(arg_prefix),
                                style="bg:#880088 #ffffff",
                                selected_style="bg:#aa00aa #ffffff",
                            )

        # User message history completion
        else:
            for msg in self.user_messages:
                if msg.lower().startswith(text.lower()):
                    yield Completion(
                        msg,
                        start_position=-len(text),
                        style="bg:#008888 #ffffff",
                        selected_style="bg:#00aaaa #ffffff",
                    )


async def connect_websocket(
    thread_id: int | None = None,
    spinner_type: str = DEFAULT_SPINNER,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    """Connect to the WebSocket server and handle the conversation."""
    # Determine WebSocket URL based on thread_id
    uri = (
        f"ws://{host}:{port}/ws/{thread_id}" if thread_id else f"ws://{host}:{port}/ws"
    )

    # Create a custom session with proper history for command history
    session_id = str(uuid.uuid4())[:8]

    # Create temporary history file for the prompt toolkit (not for message content)
    history_file = Path(".command_history").absolute()
    if not history_file.parent.exists():
        history_file.parent.mkdir(parents=True, exist_ok=True)

    # Create prompt session with history and key bindings
    prompt_style = Style.from_dict(
        {
            "prompt": "#00aa00 bold",
            "command": "#aa5500",
        }
    )

    key_bindings = KeyBindings()

    try:
        # Use a status message for the initial connection
        status = Status(f"[bold green]Connecting to {uri}...", spinner=spinner_type)
        status.start()

        try:
            websocket = await websockets.connect(uri)
            # Stop the status message after connection
            status.stop()
            console.print(f"[success]Connected to {uri}![/success]")

            # Send hello event for protocol negotiation with current timestamp
            hello = {
                "type": "hello",
                "protocol_version": "1.0",
                "since": 0,
            }
            await websocket.send(json.dumps(hello))

            # If connecting to the auto-create endpoint, get the thread ID first
            actual_thread_id = thread_id
            if not thread_id:
                response = await websocket.recv()
                thread_info = json.loads(response)
                if thread_info.get("type") == "thread_created":
                    actual_thread_id = thread_info.get("thread_id")
                    console.print(display_message(thread_info))
                    # Add to message history
                    message_history.append(thread_info)

            # Receive initial response - this will include system message about protocol
            response = await websocket.recv()
            hello_response = json.loads(response)
            console.print(display_message(hello_response))

            # Set up the prompt session with command completion
            # Refresh completer with up-to-date message history
            session = PromptSession(
                history=FileHistory(str(history_file)),
                auto_suggest=AutoSuggestFromHistory(),
                key_bindings=key_bindings,
                style=prompt_style,
                completer=DaydreamedCompleter(COMMANDS, message_history),
            )

            # Main message loop
            while True:
                # Refresh the completer with updated message history
                session.completer = DaydreamedCompleter(COMMANDS, message_history)

                # Display prompt with thread ID info
                prompt_text = f"[thread {actual_thread_id}]" if actual_thread_id else ""
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: session.prompt(f"\n{prompt_text}> ", refresh_interval=0.5),
                )

                # Handle empty input
                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith(CMD_PREFIX):
                    is_cmd, cmd_result = await handle_command(
                        user_input, actual_thread_id, websocket, "ws"
                    )
                    if is_cmd:
                        if cmd_result == "exit":
                            break
                        elif cmd_result.startswith("spinner:"):
                            spinner_type = cmd_result.split(":", 1)[1]
                        continue

                # Display user message
                user_msg = {
                    "type": "user",
                    "content": user_input,
                    "timestamp": datetime.now().timestamp(),
                    "metadata": {"session": session_id},
                }
                console.print(display_message(user_msg))

                # Send the message
                message = {"type": "message", "content": user_input}
                await websocket.send(json.dumps(message))

                # Receive responses until done
                response_status = Status(
                    "[bold green]Waiting for response...", spinner=spinner_type
                )
                response_status.start()

                try:
                    while True:
                        try:
                            response = await asyncio.wait_for(
                                websocket.recv(), timeout=2.0
                            )
                            parsed = json.loads(response)

                            # Stop the status before displaying message
                            response_status.stop()
                            console.print(display_message(parsed))

                            # Break the loop when we get a "done" event
                            if parsed.get("type") == "done":
                                break

                            # Restart status for subsequent messages
                            response_status.start()

                        except TimeoutError:
                            # Just continue waiting
                            continue
                finally:
                    # Ensure status is stopped even if there's an error
                    response_status.stop()

            # Close the websocket on exit
            await websocket.close()

        except Exception as e:
            # Make sure we stop the status if there's an error during connection
            status.stop()
            raise e

    except websockets.exceptions.ConnectionClosed as e:
        error_console.print(f"Connection closed: {e}")
    except ConnectionRefusedError:
        error_console.print("[danger]Failed to connect to server.[/danger]")
        error_console.print(
            "[info]Please run: [command]uvicorn src.backend.main:app --reload[/command][/info]"
        )
    except Exception as e:
        error_console.print(f"Error: {e}")
        # Check for various connection-related error patterns
        error_str = str(e).lower()
        if (
            "connection" in error_str
            or "connect call failed" in error_str
            or "errno 61" in error_str
            or "errno 111" in error_str
        ):
            error_console.print(
                "[info]Server may not be running. Try: [command]uvicorn src.backend.main:app --reload[/command][/info]"
            )


async def connect_sse(
    thread_id: int | None = None,
    spinner_type: str = DEFAULT_SPINNER,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    """Connect to the SSE (Server-Sent Events) server and handle the conversation."""
    # Create a custom session with proper history for command history
    session_id = str(uuid.uuid4())[:8]

    # Determine base URL for HTTP requests
    base_url = f"http://{host}:{port}"

    # Create temporary history file for the prompt toolkit
    history_file = Path(".command_history").absolute()
    if not history_file.parent.exists():
        history_file.parent.mkdir(parents=True, exist_ok=True)

    # Create prompt session with history and key bindings
    prompt_style = Style.from_dict(
        {
            "prompt": "#00aa00 bold",
            "command": "#aa5500",
        }
    )
    key_bindings = KeyBindings()

    # Initialize HTTP client
    async with httpx.AsyncClient(timeout=120.0) as client:
        # If thread_id is None, need to create a new thread first
        actual_thread_id = thread_id
        if not thread_id:
            try:
                # Use a status message for the initial connection
                status = Status(
                    "[bold green]Creating new thread...", spinner=spinner_type
                )
                status.start()

                # Create a new thread (we'll simulate this as there's no direct endpoint)
                # For now, we'll just call the WS endpoint once to get a thread ID
                temp_ws_uri = f"ws://{host}:{port}/ws"
                websocket = await websockets.connect(temp_ws_uri)
                await websocket.send(
                    json.dumps(
                        {
                            "type": "hello",
                            "protocol_version": "1.0",
                            "since": 0,
                        }
                    )
                )

                response = await websocket.recv()
                thread_info = json.loads(response)
                await websocket.close()

                if thread_info.get("type") == "thread_created":
                    actual_thread_id = thread_info.get("thread_id")
                    status.stop()
                    console.print(display_message(thread_info))
                    # Add to message history
                    message_history.append(thread_info)

                    # Also add a system message about using SSE
                    system_msg = {
                        "type": "system",
                        "content": f"Connected via SSE to thread {actual_thread_id}",
                        "timestamp": datetime.now().timestamp(),
                    }
                    console.print(display_message(system_msg))
                    message_history.append(system_msg)
                else:
                    status.stop()
                    error_console.print(
                        "[danger]Failed to create a new thread[/danger]"
                    )
                    return

            except ConnectionRefusedError:
                status.stop()
                error_console.print("[danger]Failed to connect to server.[/danger]")
                error_console.print(
                    "[info]Please run: [command]uvicorn src.backend.main:app --reload[/command][/info]"
                )
                return
            except Exception as e:
                status.stop()
                error_console.print(f"Error creating thread: {e}")
                # Check for various connection-related error patterns
                error_str = str(e).lower()
                if (
                    "connection" in error_str
                    or "connect call failed" in error_str
                    or "errno 61" in error_str
                    or "errno 111" in error_str
                ):
                    error_console.print(
                        "[info]Server may not be running. Try: [command]uvicorn src.backend.main:app --reload[/command][/info]"
                    )
                return
        else:
            # Using existing thread
            system_msg = {
                "type": "system",
                "content": f"Connected via SSE to existing thread {thread_id}",
                "timestamp": datetime.now().timestamp(),
            }
            console.print(display_message(system_msg))
            message_history.append(system_msg)

        # Test the connection to the agent endpoint
        try:
            test_endpoint = f"{base_url}/agent/{actual_thread_id}"
            # The agent endpoint only accepts POST requests, not GET
            response = await client.post(
                test_endpoint,
                json={"message": "Test connection"},
                headers={"Accept": "application/x-ndjson"},
            )
            if response.status_code >= 400:
                error_msg = {
                    "type": "error",
                    "content": f"ERROR: Agent endpoint returned status {response.status_code}. The SSE mode might not be working correctly with this backend. Consider using WebSocket mode instead.",
                    "timestamp": datetime.now().timestamp(),
                }
                console.print(display_message(error_msg))
                message_history.append(error_msg)
            else:
                # Success! No need to process the response body
                system_msg = {
                    "type": "system",
                    "content": f"Successfully connected to SSE endpoint at {test_endpoint}",
                    "timestamp": datetime.now().timestamp(),
                }
                console.print(display_message(system_msg))
                message_history.append(system_msg)
        except httpx.RequestError as e:
            error_msg = {
                "type": "system",
                "content": f"Warning: Could not connect to agent endpoint. SSE mode might have issues: {e}",
                "timestamp": datetime.now().timestamp(),
            }
            console.print(display_message(error_msg))
            message_history.append(error_msg)

        # Set up the prompt session with command completion
        session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            key_bindings=key_bindings,
            style=prompt_style,
            completer=DaydreamedCompleter(COMMANDS, message_history),
        )

        # Main message loop
        while True:
            # Refresh the completer with updated message history
            session.completer = DaydreamedCompleter(COMMANDS, message_history)

            # Display prompt with thread ID info
            prompt_text = f"[thread {actual_thread_id}]" if actual_thread_id else ""
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: session.prompt(f"\n{prompt_text}> ", refresh_interval=0.5),
            )

            # Handle empty input
            if not user_input.strip():
                continue

            # Handle commands
            if user_input.startswith(CMD_PREFIX):
                is_cmd, cmd_result = await handle_command(
                    user_input, actual_thread_id, client, "sse"
                )
                if is_cmd:
                    if cmd_result == "exit":
                        break
                    elif cmd_result.startswith("spinner:"):
                        spinner_type = cmd_result.split(":", 1)[1]
                    continue

            # Display user message
            user_msg = {
                "type": "user",
                "content": user_input,
                "timestamp": datetime.now().timestamp(),
                "metadata": {"session": session_id},
            }
            console.print(display_message(user_msg))
            message_history.append(user_msg)

            # Send the message using SSE endpoint
            endpoint = f"{base_url}/agent/{actual_thread_id}"
            json_data = {"message": user_input}

            # Use a status message while waiting for response
            response_status = Status(
                "[bold green]Waiting for response...", spinner=spinner_type
            )
            response_status.start()

            try:
                # Make the request to the streaming endpoint
                try:
                    async with client.stream(
                        "POST", endpoint, json=json_data
                    ) as response:
                        if response.status_code != 200:
                            response_status.stop()
                            error_content = f"HTTP Error: {response.status_code}"
                            try:
                                error_text = await response.aread()
                                error_content += f" - {error_text.decode('utf-8')}"
                            except Exception:
                                pass

                            error_content += "\n\nThere appears to be an issue with the SSE endpoint. This may be due to a known SQLite threading issue in the backend. You might want to try the WebSocket mode instead:\n\n`python rich_ws_client.py --protocol ws`"

                            error_msg = {
                                "type": "error",
                                "content": error_content,
                                "timestamp": datetime.now().timestamp(),
                            }
                            console.print(display_message(error_msg))
                            message_history.append(error_msg)

                            # Add a done event to complete the conversation turn
                            done_msg = {
                                "type": "done",
                                "timestamp": datetime.now().timestamp(),
                            }
                            console.print(display_message(done_msg))
                            message_history.append(done_msg)
                            continue

                        # Process the streamed response
                        # SSE format is "data: {...}\n\n"
                        buffer = ""
                        response_received = False
                        async for chunk in response.aiter_text():
                            buffer += chunk
                            response_received = True

                            # Process any complete messages in the buffer
                            while "\n\n" in buffer:
                                message_text, buffer = buffer.split("\n\n", 1)
                                if message_text.startswith("data: "):
                                    message_json = message_text[
                                        6:
                                    ]  # Remove 'data: ' prefix
                                    try:
                                        parsed = json.loads(message_json)

                                        # Stop the status before displaying message
                                        response_status.stop()
                                        console.print(display_message(parsed))
                                        message_history.append(parsed)

                                        # Break the loop when we get a "done" event
                                        if parsed.get("type") == "done":
                                            break

                                        # Restart status for subsequent messages
                                        response_status.start()
                                    except json.JSONDecodeError:
                                        response_status.stop()
                                        error_console.print(
                                            f"Invalid JSON: {message_json}"
                                        )
                                        response_status.start()

                        # If we didn't receive any response, inform the user
                        if not response_received:
                            response_status.stop()
                            error_msg = {
                                "type": "error",
                                "content": "No data received from the server. The SSE endpoint might not be working correctly. Consider using WebSocket mode instead.",
                                "timestamp": datetime.now().timestamp(),
                            }
                            console.print(display_message(error_msg))
                            message_history.append(error_msg)

                except httpx.ReadTimeout:
                    response_status.stop()
                    error_msg = {
                        "type": "error",
                        "content": "Request timed out while waiting for a response. The server might be overloaded or the SSE endpoint may have issues.",
                        "timestamp": datetime.now().timestamp(),
                    }
                    console.print(display_message(error_msg))
                    message_history.append(error_msg)

                except httpx.ConnectError:
                    response_status.stop()
                    error_msg = {
                        "type": "error",
                        "content": f"Could not connect to {endpoint}. Please check that the server is running and accessible.\n\nTo start the server, run:\n\n```\nuvicorn src.backend.main:app --reload\n```",
                        "timestamp": datetime.now().timestamp(),
                    }
                    console.print(display_message(error_msg))
                    message_history.append(error_msg)

            except Exception as e:
                response_status.stop()
                error_msg = {
                    "type": "error",
                    "content": f"Error during communication: {e!s}",
                    "timestamp": datetime.now().timestamp(),
                }
                console.print(display_message(error_msg))
                message_history.append(error_msg)
            finally:
                # Ensure status is stopped even if there's an error
                response_status.stop()

                # Add a "done" event if we didn't get one from the server
                if message_history and message_history[-1].get("type") != "done":
                    done_msg = {
                        "type": "done",
                        "timestamp": datetime.now().timestamp(),
                    }
                    console.print(display_message(done_msg))
                    message_history.append(done_msg)


def print_welcome_banner(protocol: str = "ws"):
    """Display a welcome banner with app info."""
    # Create a nicely formatted welcome banner
    title = Text("Daydreamed Client", style="title")
    version = Text("v1.0.0", style="dim")

    table = Table(show_header=False, box=box.ROUNDED, expand=True, border_style="blue")
    table.add_column("Key", style="dim", width=12)
    table.add_column("Value")

    protocol_name = "WebSocket" if protocol == "ws" else "Server-Sent Events (SSE)"
    protocol_url = (
        "ws://localhost:8000/ws"
        if protocol == "ws"
        else "http://localhost:8000/agent/{{}}"
    )

    table.add_row("Protocol", protocol_name)
    table.add_row("Server", protocol_url)
    table.add_row("Database", "Message history now stored in database")
    table.add_row("Commands", f"Type {CMD_PREFIX}help for a list of commands")
    table.add_row("Exit", f"Type {CMD_PREFIX}exit or press Ctrl+C to quit")

    # Main banner panel
    panel = Panel(
        table,
        title=title,
        subtitle=version,
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)

    # Add a note about SSE mode if that's what we're using
    if protocol == "sse":
        note_panel = Panel(
            Text(
                "NOTE: You're using SSE mode which requires the thread-safe SQLite engine configuration in the backend. "
                "If you encounter database errors, try using WebSocket mode instead with: "
                "python rich_ws_client.py --protocol ws",
                style="warning",
            ),
            border_style="warning",
            title="SSE Mode Information",
            padding=(1, 2),
        )
        console.print(note_panel)


@click.command()
@click.option(
    "--thread",
    "-t",
    type=int,
    help="Thread ID to connect to. If not provided, a new thread will be created.",
)
@click.option(
    "--spinner",
    "-s",
    type=click.Choice(SPINNERS),
    default=DEFAULT_SPINNER,
    help="Spinner animation to use for loading states.",
)
@click.option(
    "--protocol",
    "-p",
    type=click.Choice(["ws", "sse"]),
    default=DEFAULT_PROTOCOL,
    help="Protocol to use for communication (WebSocket or Server-Sent Events).",
)
@click.option(
    "--host",
    "-h",
    type=str,
    default=DEFAULT_HOST,
    help="Host address of the server.",
)
@click.option(
    "--port",
    "-P",
    type=int,
    default=DEFAULT_PORT,
    help="Port number of the server.",
)
def main(
    thread: int | None = None,
    spinner: str = DEFAULT_SPINNER,
    protocol: str = DEFAULT_PROTOCOL,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
):
    """
    Daydreamed Client - Connect to the backend and chat with the AI.

    If no thread ID is provided, a new conversation thread will be created automatically.
    You can choose between WebSocket (ws) or Server-Sent Events (sse) protocols.
    History is now stored in the database for persistence between sessions!
    """
    # Display a welcome banner
    print_welcome_banner(protocol)

    # Show connection info
    if thread:
        console.print(
            f"Connecting to existing thread: [thread_id]{thread}[/thread_id] using {protocol.upper()}"
        )
    else:
        console.print(
            f"Creating a [success]new[/success] conversation thread using {protocol.upper()}"
        )

    try:
        # Handle keyboard interrupt gracefully
        if protocol == "ws":
            asyncio.run(connect_websocket(thread, spinner, host, port))
        else:
            asyncio.run(connect_sse(thread, spinner, host, port))
    except KeyboardInterrupt:
        console.print("\n[warning]Session terminated by user[/warning]")
    except Exception as e:
        error_console.print(f"[danger]Fatal error: {e}[/danger]")
        # Check for various connection-related error patterns
        error_str = str(e).lower()
        if (
            "connection" in error_str
            or "connect call failed" in error_str
            or "errno 61" in error_str
            or "errno 111" in error_str
        ):
            error_console.print(
                "[info]Server may not be running. Try starting it with:[/info]"
            )
            error_console.print(
                "[command]uvicorn src.backend.main:app --reload[/command]"
            )
        if console.is_interactive:
            # If we're in an interactive terminal, show traceback
            console.print_exception()

    console.print(
        Panel("Thanks for using Daydreamed!", border_style="success", padding=(1, 2))
    )


if __name__ == "__main__":
    main()
