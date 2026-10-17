"""What each adapter does beyond the contract: its errors, its pages, its webhooks, its wiring."""

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from relayr.plane import PlaneTracker, plane
from relayr.plane import tracker as plane_tracker
from relayr.trackers import (
    ItemDraft,
    NotFound,
    RateLimited,
    Refused,
    TrackerError,
    Unauthorized,
    Unavailable,
)
from relayr.trackers.http import Api
from relayr.vikunja import VikunjaTracker, vikunja
from relayr.vikunja import tracker as vikunja_tracker
from tests.trackers.harnesses import SOURCE, credentials, signed
from tests.trackers.plane_api import SLUG, PlaneApi

type Handler = Callable[[httpx.Request], httpx.Response]

PLANE_SECRET = "whsec-test"


def client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def answer(
    status: int, *, json: Any = None, text: str = "", headers: dict[str, str] | None = None
) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        if json is not None:
            return httpx.Response(status, json=json, headers=headers)
        return httpx.Response(status, text=text, headers=headers)

    return handle


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


# ─── the errors both adapters share ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("handler", "error", "said"),
    [
        (timeout, Unavailable, "the tracker didn't answer: ReadTimeout"),
        (answer(503, text="down"), Unavailable, "503: down"),
        (answer(401, json={"detail": "not provided"}), Unauthorized, "not provided"),
        (answer(403, json={"detail": "Given API token is not valid"}), Unauthorized, "not valid"),
        (answer(404, json={"error": "does not exist"}), NotFound, "does not exist"),
        (answer(400, json={"name": ["This field is required."]}), Refused, '400: {"name"'),
        (answer(400, json={"code": 4019, "message": "invalid filter"}), Refused, "invalid filter"),
        (answer(422, json=["no"]), Refused, '422: ["no"]'),
    ],
)
async def test_a_trackers_failures_are_the_ports_errors(
    handler: Handler, error: type[TrackerError], said: str
) -> None:
    async with client(handler) as http:
        with pytest.raises(error, match=re.escape(said)):
            await Api(http, "https://t.test/", {}).request("GET", "/x")


@pytest.mark.parametrize(
    ("retry_after", "seconds"), [("17", 17.0), ("Fri, 1 Jan", None), (None, None)]
)
async def test_a_rate_limit_says_when_to_try_again(
    retry_after: str | None, seconds: float | None
) -> None:
    headers = {} if retry_after is None else {"retry-after": retry_after}
    body = {"error_code": 5900, "error_message": "RATE_LIMIT_EXCEEDED"}
    async with client(answer(429, json=body, headers=headers)) as http:
        with pytest.raises(RateLimited) as limited:
            await Api(http, "https://t.test", {}).request("GET", "/x")
    assert limited.value.retry_after == seconds


async def test_a_request_carries_the_key_and_takes_ten_seconds_at_most() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(409, json={"id": "1"})

    async with client(handle) as http:
        api = Api(http, "https://t.test/api/", {"X-Api-Key": "k"})
        response = await api.request("POST", "/x", json={"a": 1}, answered=(409,))
    assert response.status_code == 409
    [request] = seen
    assert (str(request.url), request.headers["x-api-key"]) == ("https://t.test/api/x", "k")
    assert request.extensions["timeout"] == {
        "connect": 10.0,
        "read": 10.0,
        "write": 10.0,
        "pool": 10.0,
    }


# ─── Plane ────────────────────────────────────────────────────────────────────


def planes(api: PlaneApi) -> PlaneTracker:
    return PlaneTracker(credentials(PlaneApi.URL), SOURCE, client=client(api.handle))


async def test_plane_reads_every_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plane_tracker, "PER_PAGE", 2)
    api = PlaneApi(secret=PLANE_SECRET)
    tracker = planes(api)
    made = [await tracker.create(api.project, f"k{n}", ItemDraft(title=f"t{n}")) for n in range(5)]
    assert [item.ref for item in (await tracker.items(api.project, None)).items] == made


async def test_plane_refuses_a_state_its_project_lacks() -> None:
    api = PlaneApi(secret=PLANE_SECRET)
    api.states = [state for state in api.states if state["group"] != "cancelled"]
    with pytest.raises(Refused, match="no cancelled state"):
        await planes(api).create(api.project, "k", ItemDraft(title="t", state="cancelled"))


async def test_plane_reads_a_triage_state_as_backlog() -> None:
    api = PlaneApi(secret=PLANE_SECRET)
    tracker = planes(api)
    ref = await tracker.create(api.project, "k", ItemDraft(title="t"))
    api.states[0]["group"] = "triage"
    item = await planes(api).item(ref)
    assert item is not None
    assert item.state == "backlog"


def plane_hook(**changes: Any) -> bytes:
    payload = {"event": "issue", "workspace_slug": SLUG, "data": {"project": "p1"}} | changes
    return json.dumps(payload).encode()


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        plane_hook(workspace_slug="globex"),
        plane_hook(data={"id": "i1"}),
    ],
)
def test_plane_nudges_only_for_its_own_workspaces_projects(body: bytes) -> None:
    tracker = planes(PlaneApi(secret=PLANE_SECRET))
    assert tracker.nudge(*signed(body, "X-Plane-Signature")) is None
    nudge = tracker.nudge(*signed(plane_hook(), "X-Plane-Signature"))
    assert nudge is not None
    assert nudge.project == "p1"


async def test_plane_finds_a_comments_place_or_starts_over() -> None:
    api = PlaneApi(secret=PLANE_SECRET)
    tracker = planes(api)
    ref = await tracker.create(api.project, "k", ItemDraft(title="t"))
    first = await tracker.comment(ref, "c1", "one")
    await tracker.comment(ref, "c2", "two")
    gone = first.model_copy(update={"id": "deleted"})
    assert [c.body for c in await tracker.comments(ref, gone)] == ["one", "two"]


# ─── Vikunja ──────────────────────────────────────────────────────────────────


def vikunjas(handler: Handler) -> VikunjaTracker:
    return VikunjaTracker(credentials("https://v.test"), SOURCE, client=client(handler))


def task(task_id: int, priority: int = 0) -> dict[str, Any]:
    return {
        "id": task_id,
        "project_id": 2,
        "index": task_id,
        "identifier": f"OPS-{task_id}",
        "title": "t",
        "description": "",
        "done": False,
        "priority": priority,
        "labels": None,
        "assignees": None,
        "updated": "2026-10-17T18:29:26Z",
    }


async def test_vikunja_reads_every_page_its_header_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vikunja_tracker, "PER_PAGE", 1)
    pages: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        pages.append(page)
        headers = {"x-pagination-total-pages": "3"}
        return httpx.Response(200, json=[task(int(page), priority=5)], headers=headers)

    found = await vikunjas(handle).items("2", None)
    assert pages == ["1", "2", "3"]
    assert [(item.ref.id, item.priority) for item in found.items] == [
        ("1", "urgent"),
        ("2", "urgent"),
        ("3", "urgent"),
    ], "its 'DO NOW' is urgent"


def test_vikunja_nudges_only_for_a_signed_webhook_it_can_read() -> None:
    tracker = vikunjas(answer(500))
    assert tracker.nudge(*signed(b"not json", "X-Vikunja-Signature")) is None
    body = json.dumps({"event_name": "task.updated", "data": {"project": {"id": 7}}}).encode()
    nudge = tracker.nudge(*signed(body, "x-vikunja-signature"))
    assert nudge is not None
    assert nudge.project == "7"


def test_each_adapter_connects_through_one_shared_client() -> None:
    http = client(answer(500))
    for connect, adapter in ((plane(http), PlaneTracker), (vikunja(http), VikunjaTracker)):
        assert isinstance(connect(credentials("https://t.test"), SOURCE), adapter)
