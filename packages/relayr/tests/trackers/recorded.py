"""Recorded exchanges with a tracker: kept from a live run, and replayed on every pull request.

A live run (`RELAYR_TEST_VIKUNJA_URL` set) records each request and response its adapter makes
through `Recorder`; with `RELAYR_RECORD=1` too, the recording replaces the test's fixture. A run
without a tracker replays the fixture through `Replayer`, which fails on any request the
recording doesn't have next, so the adapter's requests are pinned to what the tracker answered.
Keys and secrets never reach a recording: only paths, queries and JSON bodies are kept.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures"

KEPT_HEADERS = ("retry-after", "x-pagination-total-pages")
"""The response headers the adapters read."""


def _query(url: httpx.URL) -> list[list[str]]:
    return [[name, value] for name, value in url.params.multi_items()]


def _body(content: bytes) -> Any:
    return json.loads(content) if content else None


@dataclass
class Recording:
    """A test's exchanges, and what it set up around them, such as the project's id."""

    setup: dict[str, Any] = field(default_factory=dict[str, Any])
    exchanges: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])

    @classmethod
    def load(cls, path: Path) -> "Recording":
        data = json.loads(path.read_text())
        return cls(setup=data["setup"], exchanges=data["exchanges"])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"setup": self.setup, "exchanges": self.exchanges}
        path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


class Recorder(httpx.AsyncBaseTransport):
    """Passes requests to the tracker, and records each exchange."""

    def __init__(self, recording: Recording) -> None:
        self._recording = recording
        self._transport = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._transport.handle_async_request(request)
        content = await response.aread()
        self._recording.exchanges.append(
            {
                "method": request.method,
                "path": request.url.path,
                "query": _query(request.url),
                "body": _body(request.content),
                "status": response.status_code,
                "headers": {h: response.headers[h] for h in KEPT_HEADERS if h in response.headers},
                "response": _body(content),
            }
        )
        headers = [
            (name, value)
            for name, value in response.headers.multi_items()
            if name not in ("content-encoding", "content-length", "transfer-encoding")
        ]
        return httpx.Response(response.status_code, headers=headers, content=content)

    async def aclose(self) -> None:
        await self._transport.aclose()


class Replayer(httpx.AsyncBaseTransport):
    """Answers each request with the recording's next exchange, which it must match."""

    def __init__(self, recording: Recording) -> None:
        self._exchanges = list(recording.exchanges)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert self._exchanges, f"no exchange recorded for {request.method} {request.url}"
        expected = self._exchanges.pop(0)
        made = {
            "method": request.method,
            "path": request.url.path,
            "query": _query(request.url),
            "body": _body(request.content),
        }
        assert made == {k: expected[k] for k in made}, "the adapter asked otherwise than recorded"
        return httpx.Response(
            expected["status"],
            headers=expected["headers"],
            json=expected["response"],
        )

    def done(self) -> bool:
        """Whether every recorded exchange was asked for."""
        return not self._exchanges
