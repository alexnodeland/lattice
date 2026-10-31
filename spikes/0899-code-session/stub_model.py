"""Spike #899, throwaway: a scripted OpenAI-compatible model, so no real model key is needed.

It answers ``POST /v1/chat/completions`` (streamed or not) with a fixed script that
exercises a coding agent's tool loop:

1. no tool result yet: call ``write`` to create ``SPIKE.md``;
2. one tool result: call ``bash`` with ``ls``, which the session's policy sets to ``ask``;
3. otherwise: a final text answer.

LiteLLM sits in front of it (``openai/stub`` with an ``api_base``), so the coding agent
talks to LiteLLM exactly as it would with a real model.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _step(messages: list[dict[str, Any]], tools: set[str]) -> dict[str, Any]:
    claude = "Write" in tools
    tool_results = sum(1 for m in messages if m.get("role") == "tool")
    if tool_results == 0:
        path = ("file_path", "/home/agent/demo/SPIKE.md") if claude else ("filePath", "SPIKE.md")
        args = {path[0]: path[1], "content": "# Spike 899\n\nWritten in the sandbox.\n"}
        return {"tool": "Write" if claude else "write", "args": args}
    if tool_results == 1:
        return {
            "tool": "Bash" if claude else "bash",
            "args": {"command": "ls", "description": "List files"},
        }
    return {"text": "Done: I added SPIKE.md and listed the files."}


def _message(step: dict[str, Any]) -> dict[str, Any]:
    if "text" in step:
        return {"role": "assistant", "content": step["text"]}
    call = {
        "id": f"call_{int(time.time() * 1000)}",
        "type": "function",
        "function": {"name": step["tool"], "arguments": json.dumps(step["args"])},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}


class Handler(BaseHTTPRequestHandler):
    """Serves the scripted completions."""

    def do_GET(self) -> None:
        """List the one model."""
        body = json.dumps({"object": "list", "data": [{"id": "stub", "object": "model"}]})
        self._send(200, body.encode(), "application/json")

    def do_POST(self) -> None:
        """Answer a chat completion with the script's next step."""
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        tools = {t.get("function", {}).get("name") for t in request.get("tools") or []}
        message = _message(_step(request.get("messages", []), tools))
        reason = "tool_calls" if "tool_calls" in message else "stop"
        sys.stderr.write(f"stub: {reason} after {len(request.get('messages', []))} messages\n")
        base = {"id": "stub-1", "created": int(time.time()), "model": "stub"}
        if not request.get("stream"):
            choice = {"index": 0, "message": message, "finish_reason": reason}
            usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            body = {**base, "object": "chat.completion", "choices": [choice], "usage": usage}
            self._send(200, json.dumps(body).encode(), "application/json")
            return
        delta: dict[str, Any] = {"role": "assistant", "content": message["content"]}
        if "tool_calls" in message:
            delta["tool_calls"] = [{"index": 0, **message["tool_calls"][0]}]
        chunks = [
            {"index": 0, "delta": delta, "finish_reason": None},
            {"index": 0, "delta": {}, "finish_reason": reason},
        ]
        events = b"".join(
            b"data: "
            + json.dumps({**base, "object": "chat.completion.chunk", "choices": [c]}).encode()
            + b"\n\n"
            for c in chunks
        )
        self._send(200, events + b"data: [DONE]\n\n", "text/event-stream")

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), Handler).serve_forever()
