"""A fake of the parts of Langfuse's public API that evalr's adapters reach through the SDK.

It runs behind the real ``Langfuse`` client's own ``httpx`` transport, so the SDK's requests,
pagination and parsing are exercised without a network. Items keep their history, so reading
a dataset at a time (``version``) returns its items as they were then, as Langfuse does.
"""

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote

import httpx
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

START = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FakeLangfuse:
    def __init__(self) -> None:
        self.ticks = 0
        self.datasets: dict[str, dict[str, Any]] = {}
        self.history: dict[str, list[tuple[datetime, dict[str, Any]]]] = {}
        self.scores: dict[str, dict[str, Any]] = {}
        self.writes: list[str] = []

    def now(self) -> datetime:
        self.ticks += 1
        return START + timedelta(milliseconds=self.ticks)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body: Any = json.loads(request.content) if request.content else None
        if path == "/api/public/v2/datasets" and method == "POST":
            return self.create_dataset(body)
        if path.startswith("/api/public/v2/datasets/") and method == "GET":
            name = unquote(path.removeprefix("/api/public/v2/datasets/"))
            if name not in self.datasets:
                return httpx.Response(404, json={"message": f"Dataset {name} not found"})
            return httpx.Response(200, json=self.datasets[name])
        if path == "/api/public/dataset-items" and method == "POST":
            return self.create_item(body)
        if path == "/api/public/dataset-items" and method == "GET":
            return self.list_items(dict(request.url.params))
        if path == "/api/public/ingestion" and method == "POST":
            return self.ingest(body)
        if path == "/api/public/projects" and method == "GET":
            return httpx.Response(200, json={"data": [{"id": "project", "name": "evalr"}]})
        return httpx.Response(404, json={"message": f"{method} {path} is not faked"})

    def create_dataset(self, body: dict[str, Any]) -> httpx.Response:
        moment = stamp(self.now())
        existing = self.datasets.get(body["name"])
        self.datasets[body["name"]] = {
            "id": existing["id"] if existing else str(uuid.uuid4()),
            "name": body["name"],
            "description": body.get("description"),
            "metadata": body.get("metadata"),
            "inputSchema": body.get("inputSchema"),
            "expectedOutputSchema": body.get("expectedOutputSchema"),
            "projectId": "project",
            "createdAt": existing["createdAt"] if existing else moment,
            "updatedAt": moment,
        }
        return httpx.Response(200, json=self.datasets[body["name"]])

    def create_item(self, body: dict[str, Any]) -> httpx.Response:
        dataset = self.datasets[body["datasetName"]]
        item_id = body.get("id") or str(uuid.uuid4())
        moment = self.now()
        history = self.history.setdefault(item_id, [])
        state = {
            "id": item_id,
            "status": body.get("status") or "ACTIVE",
            "input": body.get("input"),
            "expectedOutput": body.get("expectedOutput"),
            "metadata": body.get("metadata"),
            "sourceTraceId": body.get("sourceTraceId"),
            "sourceObservationId": body.get("sourceObservationId"),
            "datasetId": dataset["id"],
            "datasetName": dataset["name"],
            "createdAt": history[0][1]["createdAt"] if history else stamp(moment),
            "updatedAt": stamp(moment),
            "mediaReferences": [],
        }
        history.append((moment, state))
        self.writes.append(item_id)
        return httpx.Response(200, json=state)

    def list_items(self, params: dict[str, str]) -> httpx.Response:
        name = params["datasetName"]
        version = datetime.fromisoformat(params["version"]) if "version" in params else None
        items = []
        for history in self.history.values():
            states = [s for t, s in history if version is None or t <= version]
            if states and states[-1]["datasetName"] == name:
                items.append(states[-1])
        page, limit = int(params.get("page", 1)), int(params.get("limit", 50))
        pages = max(1, -(-len(items) // limit))
        return httpx.Response(
            200,
            json={
                "data": items[(page - 1) * limit : page * limit],
                "meta": {
                    "page": page,
                    "limit": limit,
                    "totalItems": len(items),
                    "totalPages": pages,
                },
            },
        )

    def ingest(self, body: dict[str, Any]) -> httpx.Response:
        successes = []
        for event in body["batch"]:
            if event["type"] == "score-create":
                self.scores[event["body"]["id"]] = event["body"]
            successes.append({"id": event["id"], "status": 201})
        return httpx.Response(207, json={"successes": successes, "errors": []})


@contextmanager
def connected(server: FakeLangfuse) -> Iterator[tuple[Langfuse, InMemorySpanExporter]]:
    """A real Langfuse client on the fake server, exporting its spans to memory."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    client = Langfuse(
        public_key=f"pk-{uuid.uuid4()}",
        secret_key="sk",
        base_url="http://langfuse.test",
        span_exporter=exporter,
        tracer_provider=provider,
        flush_interval=0.05,
        httpx_client=httpx.Client(transport=httpx.MockTransport(server.handler)),
    )
    try:
        yield client, exporter
    finally:
        client.shutdown()
        provider.shutdown()
