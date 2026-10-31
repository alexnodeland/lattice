"""Spike #899, throwaway: lattice's side of an ACP agent, over the sandbox's exec stream.

Runs the agent's ACP command with ``docker exec -i`` (stdio is the exec stream), then
``initialize``, ``session/new`` and ``session/prompt``. It answers the agent's requests
the way the port's adapter would: ``session/request_permission`` (allow once, as a person
would from the thread) and ``fs/*`` (served from the working tree, through the exec).
Writes a timeline (seconds since start) to stdout as JSON lines.

Usage: ``drive_acp.py <container> <cwd> <task> -- <agent command...>``.
"""

import json
import subprocess
import sys
import time
from typing import Any

CONTAINER, CWD, TASK = sys.argv[1], sys.argv[2], sys.argv[3]
COMMAND = sys.argv[sys.argv.index("--") + 1 :]
START = time.monotonic()


def log(kind: str, **fields: Any) -> None:
    """Write one timeline entry."""
    entry = {"t": round(time.monotonic() - START, 2), "kind": kind, **fields}
    sys.stdout.write(json.dumps(entry)[:600] + "\n")
    sys.stdout.flush()


def sandbox_exec(*args: str, stdin: str | None = None) -> str:
    """Run a command in the sandbox."""
    flags = ["-i"] if stdin is not None else []
    run = ["docker", "exec", *flags, "-w", CWD, CONTAINER, *args]
    return subprocess.run(run, input=stdin, capture_output=True, text=True, check=True).stdout


def serve(method: str, params: dict[str, Any]) -> Any:
    """Answer one request from the agent."""
    log("request", method=method)
    if method == "session/request_permission":
        options = params["options"]
        chosen = next(o for o in options if o["kind"] == "allow_once")
        log(
            "permission", tool=params["toolCall"].get("title"), options=[o["kind"] for o in options]
        )
        return {"outcome": {"outcome": "selected", "optionId": chosen["optionId"]}}
    if method == "fs/read_text_file":
        return {"content": sandbox_exec("cat", params["path"])}
    if method == "fs/write_text_file":
        sandbox_exec("sh", "-c", 'cat > "$1"', "-", params["path"], stdin=params["content"])
        return {}
    raise ValueError(method)


def main() -> None:
    """Run one prompt to its stop reason."""
    agent = subprocess.Popen(
        ["docker", "exec", "-i", "-w", CWD, CONTAINER, *COMMAND],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert agent.stdin is not None
    assert agent.stdout is not None
    next_id = 0

    def request(method: str, params: dict[str, Any]) -> Any:
        nonlocal next_id
        next_id += 1
        message = {"jsonrpc": "2.0", "id": next_id, "method": method, "params": params}
        agent.stdin.write(json.dumps(message) + "\n")
        agent.stdin.flush()
        for line in agent.stdout:
            incoming = json.loads(line)
            if "method" in incoming and "id" in incoming:
                reply = {"jsonrpc": "2.0", "id": incoming["id"]}
                reply["result"] = serve(incoming["method"], incoming["params"])
                agent.stdin.write(json.dumps(reply) + "\n")
                agent.stdin.flush()
            elif "method" in incoming:
                update = incoming["params"].get("update", {})
                log("update", update=update.get("sessionUpdate"), title=update.get("title"))
            elif incoming.get("id") == next_id:
                if "error" in incoming:
                    raise RuntimeError(incoming["error"])
                return incoming["result"]
        raise RuntimeError("the agent closed its stdout")

    capabilities = {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": False}
    init = request("initialize", {"protocolVersion": 1, "clientCapabilities": capabilities})
    log("initialized", agent=init.get("agentInfo"), capabilities=init.get("agentCapabilities"))
    session = request("session/new", {"cwd": CWD, "mcpServers": []})
    log("session", id=session["sessionId"], modes=session.get("modes"))
    prompt = [{"type": "text", "text": TASK}]
    result = request("session/prompt", {"sessionId": session["sessionId"], "prompt": prompt})
    log("stopped", result=result)
    agent.stdin.close()
    agent.wait(timeout=30)


if __name__ == "__main__":
    main()
