"""The server end to end: the agent drafts a doc, proposes a plan, and a person reviews it."""

from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from mcp import Client
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

import docplan.app
from artifactr import new_id
from conftest import Script, call, say, wait_for
from docplan.app import create_app, open_database

BASE = "/v1/workspaces/main"


def command(client: TestClient, **body: Any) -> dict[str, Any]:
    frame = {"type": "command", "command_id": new_id("cmd"), "command": body}
    return client.post(f"{BASE}/commands", json=frame).json()


def ask(client: TestClient, content: str, *, runs: int) -> None:
    """Post a message in thread t1 and wait for the agent's ``runs``-th run to end."""
    command(client, type="post_message", thread_id="t1", content=content)
    wait_for(lambda: len(events(client, "run_ended")) >= runs)


def events(client: TestClient, event_type: str) -> list[dict[str, Any]]:
    log = client.get(f"{BASE}/events").json()
    return [envelope["event"] for envelope in log if envelope["event"]["type"] == event_type]


def accept_the_proposal(client: TestClient) -> None:
    [proposal] = client.get(f"{BASE}/proposals").json()
    result = command(
        client, type="respond_to_proposal", proposal_id=proposal["id"], decision="accept"
    )
    assert result["ok"], result


def test_the_agent_drafts_a_doc_and_the_plan_is_reviewed(
    client: TestClient, script: Script
) -> None:
    command(client, type="create_thread", thread_id="t1")
    script.steps += [
        call("create_artifact", kind="doc", data={"title": "Launch", "text": "Ship on Friday."}),
        call("create_artifact", kind="plan", data={"goal": "Ship search"}),
        say("I drafted the doc and proposed a plan."),
    ]
    ask(client, "Plan the launch", runs=1)
    [doc] = client.get(f"{BASE}/artifacts").json()
    assert (doc["kind"], doc["data"]["title"]) == ("doc", "Launch")
    accept_the_proposal(client)
    plan = client.get(f"{BASE}/artifacts", params={"kind": "plan"}).json()[0]

    script.steps += [
        call("add_task", plan_id=plan["id"], title="Write the announcement", owner="alice"),
        say("I proposed a task."),
    ]
    ask(client, "Add the announcement", runs=2)
    accept_the_proposal(client)
    tasks = client.get(f"{BASE}/artifacts/{plan['id']}").json()["data"]["tasks"]
    [(task_id, task)] = tasks.items()
    assert (task["title"], task["status"], task["owner"]) == (
        "Write the announcement",
        "todo",
        "alice",
    )

    script.steps += [
        call("set_task_status", plan_id=plan["id"], task_id="task_nope", status="doing"),
        call("set_task_status", plan_id=plan["id"], task_id=task_id, status="doing"),
        say("Started it."),
    ]
    ask(client, "Alice started the announcement", runs=3)
    assert [r["status"] for r in events(client, "tool_returned")][-2:] == ["retry", "ok"]
    accept_the_proposal(client)
    changed = events(client, "artifact_changed")[-1]
    assert changed["summary"] == "'Write the announcement' is doing"


@pytest.mark.parametrize(
    ("headers", "params", "user"),
    [({}, {}, "alice"), ({"x-user": ""}, {"user": "bob"}, "bob"), ({"x-user": ""}, {}, "guest")],
)
def test_demo_authentication_trusts_the_caller(
    client: TestClient, headers: dict[str, str], params: dict[str, str], user: str
) -> None:
    frame = {"type": "command", "command_id": "c1", "command": {"type": "create_thread"}}
    client.post(f"{BASE}/commands", json=frame, headers=headers, params=params)
    [created] = client.get(f"{BASE}/events").json()
    assert created["actor"]["id"] == user


def test_workspaces_can_live_in_a_database(
    tmp_path: Path, script: Script, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCPLAN_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'docplan.db'}")
    with TestClient(create_app(model=script.model), headers={"x-user": "alice"}) as client:
        command(client, type="create_artifact", kind="doc", data={"title": "Kept"})
    with TestClient(create_app(model=script.model), headers={"x-user": "alice"}) as client:
        [doc] = client.get(f"{BASE}/artifacts").json()
    assert doc["data"]["title"] == "Kept", "a restarted server finds it"


def test_other_databases_get_a_plain_async_engine() -> None:
    assert open_database("postgresql+asyncpg://localhost/docplan").dialect.name == "postgresql"


def test_the_root_describes_the_surfaces(client: TestClient) -> None:
    assert client.get("/").json()["mcp"] == "/mcp"


async def test_mcp_clients_work_in_the_same_workspace(server: str) -> None:
    async with Client(f"{server}/mcp/") as mcp:
        created = await mcp.call_tool(
            "create_artifact", {"workspace_id": "main", "kind": "doc", "data": {"title": "Notes"}}
        )
        assert not created.is_error
    async with httpx.AsyncClient(base_url=server, headers={"x-user": "alice"}) as http:
        [doc] = (await http.get(f"{BASE}/artifacts")).json()
    assert (doc["kind"], doc["data"]["title"]) == ("doc", "Notes")
    assert doc["updated_by"] == {"kind": "external_agent", "client_id": "mcp", "name": "MCP client"}


def test_main_serves_on_the_configured_address(monkeypatch: pytest.MonkeyPatch) -> None:
    served: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: served.update(kwargs))
    monkeypatch.setenv("DOCPLAN_PORT", "9000")
    docplan.app.main()
    assert served == {"host": "127.0.0.1", "port": 9000}


def test_main_sets_up_telemetry_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[dict[str, Any]] = []
    shut_down: list[bool] = []

    class Handle:
        langfuse = None
        tracer_provider = None  # the global ones
        meter_provider = None

        def capability(self) -> Instrumentation:
            return Instrumentation(settings=InstrumentationSettings())

        def instrument_app(self, app: object) -> None:
            pass

        def shutdown(self) -> None:
            shut_down.append(True)

    def configure(**options: Any) -> Handle:
        configured.append(options)
        return Handle()

    monkeypatch.setattr(docplan.app, "configure_telemetry", configure)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "LANGFUSE_PUBLIC_KEY", "DOCPLAN_LANGFUSE"):
        monkeypatch.delenv(name, raising=False)
    assert docplan.app.telemetry_from_environment() is None
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
    docplan.app.main()
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-1")
    docplan.app.main()
    monkeypatch.setenv("DOCPLAN_LANGFUSE", "scores")
    docplan.app.main()
    assert [options["langfuse"] for options in configured] == [None, "traces", "scores"]
    assert {options["service_name"] for options in configured} == {"docplan"}
    assert shut_down == [True, True, True]
