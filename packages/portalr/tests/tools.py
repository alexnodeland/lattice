"""A stand-in for a tool's HTTP API: it answers each path as a test scripts, and keeps requests."""

from collections.abc import Callable
from typing import Any

import httpx

Answer = Callable[[httpx.Request], httpx.Response]


def json(body: Any, status: int = 200) -> Answer:
    """Answer every request with this JSON."""
    return lambda _request: httpx.Response(status, json=body)


def fails(error: type[httpx.TransportError] = httpx.ConnectError) -> Answer:
    """Fail every request, as a tool that is down does."""

    def answer(request: httpx.Request) -> httpx.Response:
        raise error("down", request=request)

    return answer


class Tool:
    """A tool's API, by path."""

    def __init__(self, paths: dict[str, Answer] | None = None) -> None:
        self.paths: dict[str, Answer] = dict(paths or {})
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.paths.get(request.url.path)
        return answer(request) if answer else httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]
