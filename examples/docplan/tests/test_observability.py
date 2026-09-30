"""docplan with its telemetry, Langfuse and LiteLLM configured: nothing leaves the process."""

import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import Script, say, wait_for
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.models.openai import OpenAIChatModel

from artifactr import new_id
from artifactr.otel import configure_telemetry
from docplan.agent import build_agent
from docplan.app import create_app


class FakeLangfuse:
    """Langfuse's score-config and ingestion endpoints, in memory."""

    def __init__(self) -> None:
        self.configs: list[str] = []
        self.scores: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/public/score-configs" and request.method == "GET":
            meta = {"page": 1, "limit": 100, "totalItems": 0, "totalPages": 0}
            return httpx.Response(200, json={"data": [], "meta": meta})
        body = json.loads(request.content)
        if request.url.path == "/api/public/score-configs":
            self.configs.append(body["name"])
            created = {"id": body["name"], "createdAt": "2026-09-28T00:00:00Z"}
            created |= {"updatedAt": "2026-09-28T00:00:00Z", "projectId": "p", "isArchived": False}
            return httpx.Response(200, json=body | created)
        self.scores += [e["body"] for e in body["batch"] if e["type"] == "score-create"]
        return httpx.Response(207, json={"successes": [], "errors": []})


def test_ratings_reach_langfuse_on_the_turns_trace(tmp_path: Path) -> None:
    langfuse = FakeLangfuse()
    spans = InMemorySpanExporter()
    telemetry = configure_telemetry(
        service_name="docplan",
        instrument=(),
        logs=False,
        set_global=False,
        span_exporter=spans,
        metric_reader=InMemoryMetricReader(),
        langfuse="traces",
        langfuse_options={
            "public_key": f"pk-lf-{uuid.uuid4()}",
            "secret_key": "sk-lf-test",
            "base_url": "http://langfuse.test",
            "httpx_client": httpx.Client(transport=httpx.MockTransport(langfuse.handle)),
            "span_exporter": InMemorySpanExporter(),
        },
    )
    app = create_app(
        model=Script(say("Hello.")).model,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'docplan.db'}",
        telemetry=telemetry,
    )
    base = "/v1/workspaces/main"

    def command(client: TestClient, **body: Any) -> dict[str, Any]:
        frame = {"type": "command", "command_id": new_id("cmd"), "command": body}
        return client.post(f"{base}/commands", json=frame).json()

    def ended(client: TestClient) -> list[dict[str, Any]]:
        log = client.get(f"{base}/events").json()
        return [e for e in log if e["event"]["type"] == "run_ended"]

    try:
        with TestClient(app, headers={"x-user": "alice"}) as client:
            assert langfuse.configs == [
                "rating.stars",
                "rating.comment",
                "edit_size.too_big",
                "edit_size.comment",
                "task_completion.completed",
                "task_completion.quality",
                "task_completion.reason",
            ]
            command(client, type="create_thread", thread_id="t1")
            command(client, type="post_message", thread_id="t1", content="Hi")
            wait_for(lambda: ended(client))
            [run] = ended(client)
            target = {"kind": "turn", "run_id": run["run_id"]}
            rated = command(
                client,
                type="give_feedback",
                feedback_type="rating",
                target=target,
                value={"stars": 4},
            )
            assert rated["ok"], rated
            trace_ids = client.get(f"{base}/runs/{run['run_id']}").json()["trace_ids"]

            def scored() -> bool:
                assert telemetry.langfuse is not None
                telemetry.langfuse.flush()
                return bool(langfuse.scores)

            wait_for(scored)
    finally:
        telemetry.shutdown()
    [score] = langfuse.scores
    assert (score["name"], score["value"], score["traceId"]) == ("rating.stars", 4.0, trace_ids[-1])
    names = {span.name for span in spans.get_finished_spans()}
    assert {"invoke_workflow turn", "GET /v1/workspaces/{workspace_id}/events"} <= names


def test_the_agent_can_use_a_litellm_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCPLAN_LITELLM_URL", "http://litellm:4000")
    agent = build_agent()
    assert isinstance(agent.model, OpenAIChatModel)
    assert (agent.model.model_name, agent.model.system) == ("claude-sonnet", "litellm")
    assert "LiteLLMGateway" in repr(agent.root_capability)
