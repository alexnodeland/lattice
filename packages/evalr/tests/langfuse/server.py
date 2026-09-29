"""A fake of the parts of Langfuse's public API that evalr's adapters reach through the SDK.

It runs behind the real ``Langfuse`` client's own ``httpx`` transport, so the SDK's requests,
pagination and parsing are exercised without a network. It behaves as Langfuse 4.46 does, as
evalr's check against a real Langfuse found (issue #26):

- Every write of an item is a new version of it, created at the time of the write, so reading
  a dataset at a time (``version``) returns its items as they were then.
- Only active items are listed, at any time: an archived or deleted item is left out of the
  list, though an archived one can still be read by its id.
- A write that leaves a field empty (``null``) keeps the item's value for it; only deleting the
  item clears it.
- JSON is kept as JavaScript keeps it, so a whole-number float comes back as an integer.
"""

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast
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
        self.history: dict[str, list[tuple[datetime, dict[str, Any] | None]]] = {}
        """Every version of every item, by id; ``None`` where the item was deleted."""
        self.scores: dict[str, dict[str, Any]] = {}
        self.score_times: dict[str, str] = {}
        """When each score was given, by id: its ingestion event's timestamp."""
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
        if path.startswith("/api/public/dataset-items/") and method == "GET":
            return self.get_item(path.removeprefix("/api/public/dataset-items/"))
        if path.startswith("/api/public/dataset-items/") and method == "DELETE":
            return self.delete_item(path.removeprefix("/api/public/dataset-items/"))
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
            "metadata": as_javascript(body.get("metadata")),
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
        before = (history[-1][1] if history else None) or {}
        kept = {
            field: as_javascript(body[field]) if body.get(field) is not None else before.get(field)
            for field in (
                "input",
                "expectedOutput",
                "metadata",
                "sourceTraceId",
                "sourceObservationId",
            )
        }
        state = {
            "id": item_id,
            "status": body.get("status") or "ACTIVE",
            **kept,
            "datasetId": dataset["id"],
            "datasetName": dataset["name"],
            "createdAt": stamp(moment),
            "updatedAt": stamp(moment),
            "mediaReferences": [],
        }
        history.append((moment, state))
        self.writes.append(item_id)
        return httpx.Response(200, json=state)

    def item(self, item_id: str) -> dict[str, Any]:
        """The item as it is now; it must not be deleted."""
        latest = self.history[item_id][-1][1]
        assert latest is not None
        return latest

    def get_item(self, item_id: str) -> httpx.Response:
        history = self.history.get(item_id)
        if not history or history[-1][1] is None:
            return httpx.Response(404, json={"message": "Dataset item not found"})
        return httpx.Response(200, json=history[-1][1])

    def delete_item(self, item_id: str) -> httpx.Response:
        self.history[item_id].append((self.now(), None))
        self.writes.append(item_id)
        return httpx.Response(200, json={"message": "Dataset item successfully deleted"})

    def list_items(self, params: dict[str, str]) -> httpx.Response:
        name = params["datasetName"]
        version = datetime.fromisoformat(params["version"]) if "version" in params else None
        items: list[dict[str, Any]] = []
        for history in self.history.values():
            states = [s for t, s in history if version is None or t <= version]
            latest = states[-1] if states else None
            if latest and latest["datasetName"] == name and latest["status"] == "ACTIVE":
                items.append(latest)
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
                self.score_times[event["body"]["id"]] = event["timestamp"]
            successes.append({"id": event["id"], "status": 201})
        return httpx.Response(207, json={"successes": successes, "errors": []})


def as_javascript(value: Any) -> Any:
    """JSON as Langfuse, in JavaScript, keeps it: a whole-number float is an integer."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [as_javascript(v) for v in cast(list[Any], value)]
    if isinstance(value, dict):
        return {k: as_javascript(v) for k, v in cast(dict[str, Any], value).items()}
    return value


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
