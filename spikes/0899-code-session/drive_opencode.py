"""Spike #899, throwaway: lattice's side of an opencode session, over ``opencode serve``'s API.

Creates a session, follows ``/event`` (SSE) in a thread, sends the task with
``prompt_async``, answers each permission ask (as a person would from the thread), and
reconciles against ``/session/status`` and ``/permission`` rather than trusting the stream.
Writes a timeline (seconds since start) to stdout as JSON lines.

Usage: ``drive_opencode.py <base-url> <password> <task>``.
"""

import base64
import json
import sys
import threading
import time
import urllib.request
from typing import Any

BASE, PASSWORD, TASK = sys.argv[1], sys.argv[2], sys.argv[3]
AUTH = "Basic " + base64.b64encode(f"opencode:{PASSWORD}".encode()).decode()
START = time.monotonic()


def log(kind: str, **fields: Any) -> None:
    """Write one timeline entry."""
    entry = {"t": round(time.monotonic() - START, 2), "kind": kind, **fields}
    sys.stdout.write(json.dumps(entry) + "\n")
    sys.stdout.flush()


def call(method: str, path: str, body: Any = None) -> Any:
    """Call opencode's API."""
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": AUTH, "Content-Type": "application/json"}
    request = urllib.request.Request(BASE + path, data, headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def follow() -> None:
    """Log every event's type from the SSE stream."""
    request = urllib.request.Request(BASE + "/event", headers={"Authorization": AUTH})
    with urllib.request.urlopen(request, timeout=600) as stream:
        for line in stream:
            if line.startswith(b"data: "):
                event = json.loads(line[6:])
                props = event.get("properties", {})
                part = props.get("part", {})
                log("event", type=event.get("type"), part=part.get("type"), tool=part.get("tool"))


def main() -> None:
    """Run the session to idle."""
    threading.Thread(target=follow, daemon=True).start()
    session = call("POST", "/session", {"title": "spike 899"})
    log("session", id=session["id"])
    call(
        "POST",
        f"/session/{session['id']}/prompt_async",
        {"parts": [{"type": "text", "text": TASK}]},
    )
    log("prompted")
    answered: set[str] = set()
    busy_seen = False
    while time.monotonic() - START < 300:
        for ask in call("GET", "/permission") or []:
            if ask["id"] not in answered:
                log("permission", ask=ask)
                call("POST", f"/permission/{ask['id']}/reply", {"reply": "once"})
                answered.add(ask["id"])
                log("answered", id=ask["id"])
        status = (call("GET", "/session/status") or {}).get(session["id"], {"type": "idle"})
        busy_seen = busy_seen or status.get("type") != "idle"
        if busy_seen and status.get("type") == "idle":
            break
        time.sleep(0.25)
    log("idle")
    diff = call("GET", f"/session/{session['id']}/diff")
    log("diff", diff=diff)
    messages = call("GET", f"/session/{session['id']}/message")
    parts = [p.get("type") for m in messages for p in m.get("parts", [])]
    log("messages", count=len(messages), parts=parts)


if __name__ == "__main__":
    main()
