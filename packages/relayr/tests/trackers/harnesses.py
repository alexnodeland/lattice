"""The trackers the contract test runs against, each with what a test does in it as a person.

- `fake`: relayr's `FakeTracker`.
- `vikunja`: Vikunja's recorded exchanges, replayed; or, with `RELAYR_TEST_VIKUNJA_URL` set, a
  live Vikunja, recorded (and saved as the fixtures with `RELAYR_RECORD=1`). A live run registers
  a user of its own, with an API token, and each test makes a project: the instance must allow
  registration, as `moon run relayr:vikunja-up` starts it.
- `plane`: Plane's recorded exchanges, replayed; or, with `RELAYR_TEST_PLANE_URL` set, a live Plane
  CE, recorded (and saved as the fixtures with `RELAYR_RECORD=1`). A live run signs up a user of
  its own in the web app, with a workspace and an API key, and each test makes a project; the
  instance must allow sign-up, and its `API_KEY_RATE_LIMIT` must be well above its default of
  60 a minute.
"""

import asyncio
import hashlib
import hmac
import json
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx

from relayr.plane import PlaneTracker
from relayr.trackers import FakeTracker, ItemRef, Tracker, TrackerCredentials
from relayr.trackers.fake import SIGNATURE
from relayr.vikunja import VikunjaTracker
from tests.clock import FakeClock
from tests.trackers.recorded import FIXTURES, Recorder, Recording, Replayer

SOURCE = "lattice:acme/ops"
SECRET = "whsec-test"
VIKUNJA_URL = os.environ.get("RELAYR_TEST_VIKUNJA_URL")
PLANE_URL = os.environ.get("RELAYR_TEST_PLANE_URL")
RECORD = os.environ.get("RELAYR_RECORD") == "1"

type Delivery = tuple[Mapping[str, str], bytes]


@dataclass
class Harness:
    """A tracker for one contract test, and what a person does in it."""

    tracker: Tracker
    project: str
    delivery: Delivery
    """A webhook the tracker signed with `SECRET`, about `delivered`."""

    delivered: str
    link: Callable[[ItemRef], str]
    """The link the tracker's web app has for an item."""

    add: Callable[[str], Awaitable[ItemRef]]
    """File an item with a title, as a person does, with no key."""

    reply: Callable[[ItemRef, str], Awaitable[None]]
    """Comment on an item, as a person does."""

    delete: Callable[[ItemRef], Awaitable[None]]
    archive: Callable[[ItemRef], None] | None
    """Archive an item, if the tracker can: Vikunja archives projects, not tasks."""

    tick: Callable[[], Awaitable[None]] = field(default=lambda: _idle())
    """Let a second pass: a tracker that keeps `updated` to the second needs one between
    changes a test tells apart."""


def credentials(base_url: str, api_key: str = "key") -> TrackerCredentials:
    return TrackerCredentials(
        base_url=base_url, api_key=api_key, webhook_secret=SECRET, workspace="acme"
    )


def signed(body: bytes, header: str) -> Delivery:
    return {header: hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()}, body


@asynccontextmanager
async def fake() -> AsyncIterator[Harness]:
    clock = FakeClock()
    tracker = FakeTracker(dedupes=True, clock=clock)

    async def tick() -> None:
        clock.advance(timedelta(seconds=1))

    async def add(title: str) -> ItemRef:
        return tracker.add("ops", title)

    async def reply(ref: ItemRef, body: str) -> None:
        tracker.reply(ref, body)

    async def delete(ref: ItemRef) -> None:
        tracker.delete(ref)

    yield Harness(
        tracker=tracker.connect(credentials("https://fake.test"), SOURCE),
        project="ops",
        delivery=signed(json.dumps({"project": "ops"}).encode(), SIGNATURE),
        delivered="ops",
        link=lambda ref: f"https://fake.test/ops/{ref.number}",
        add=add,
        reply=reply,
        delete=delete,
        archive=tracker.archive,
        tick=tick,
    )


@asynccontextmanager
async def plane(test: str) -> AsyncIterator[Harness]:
    fixture = FIXTURES / "plane" / f"{test}.json"
    hook = json.loads((FIXTURES / "plane" / "webhook.json").read_text())
    session: _PlaneSession | None = None
    if PLANE_URL is None:
        recording = Recording.load(fixture)
        replayer = Replayer(recording)
        base, key = "https://plane.test", "key"
        transport: httpx.AsyncBaseTransport = replayer
    else:
        base, replayer = PLANE_URL, None
        session = _PLANE_SESSIONS.get(base) or await _plane_session(base)
        _PLANE_SESSIONS[base] = session
        recording = Recording(setup=await _plane_project(base, session))
        key, transport = session.key, _Settling(recording)
    workspace, project = recording.setup["workspace"], recording.setup["project"]
    identifier = recording.setup["identifier"]
    async with httpx.AsyncClient(transport=transport) as client:
        api = f"{base}/api/v1/workspaces/{workspace}/projects/{project}/work-items"
        headers = {"X-Api-Key": key}

        async def add(title: str) -> ItemRef:
            made = (await client.post(f"{api}/", json={"name": title}, headers=headers)).json()
            number = made["sequence_id"]
            return ItemRef(
                project=project, id=made["id"], number=number, name=f"{identifier}-{number}"
            )

        async def reply(ref: ItemRef, body: str) -> None:
            await client.post(
                f"{api}/{ref.id}/comments/", json={"comment_html": body}, headers=headers
            )

        async def delete(ref: ItemRef) -> None:
            await client.delete(f"{api}/{ref.id}/", headers=headers)

        def archive(ref: ItemRef) -> None:
            """Archive in the web app, which archives only a done item; a replay has done so."""
            if session is not None:
                _plane_archive(base, session, workspace, project, ref.id)

        credentials = TrackerCredentials(
            base_url=base, api_key=key, webhook_secret=SECRET, workspace=workspace
        )
        yield Harness(
            tracker=PlaneTracker(credentials, SOURCE, client=client),
            project=project,
            delivery=_addressed(hook, workspace),
            delivered=json.loads(hook["body"])["data"]["project"],
            link=lambda ref: f"{base}/{workspace}/browse/{ref.name}/",
            add=add,
            reply=reply,
            delete=delete,
            archive=archive,
        )
    if replayer is not None:
        assert replayer.done(), "the adapter asked for less than was recorded"
    elif RECORD:
        recording.save(fixture)


@asynccontextmanager
async def vikunja(test: str) -> AsyncIterator[Harness]:
    fixture = FIXTURES / "vikunja" / f"{test}.json"
    hook = json.loads((FIXTURES / "vikunja" / "webhook.json").read_text())
    delivery: Delivery = (hook["headers"], hook["body"].encode())
    delivered = str(json.loads(hook["body"])["data"]["project"]["id"])
    if VIKUNJA_URL is None:
        recording = Recording.load(fixture)
        replayer = Replayer(recording)
        base, key, tick = "https://vikunja.test", "key", _idle
        transport: httpx.AsyncBaseTransport = replayer
    else:
        recording = Recording(setup={"project": None})
        base, key, recording.setup["project"] = VIKUNJA_URL, *await _provision(VIKUNJA_URL)
        transport, tick, replayer = Recorder(recording), _second, None
    project = str(recording.setup["project"])
    async with httpx.AsyncClient(transport=transport) as client:
        api = f"{base}/api/v1"
        headers = {"Authorization": f"Bearer {key}"}

        async def add(title: str) -> ItemRef:
            made = await client.put(
                f"{api}/projects/{project}/tasks", json={"title": title}, headers=headers
            )
            task = made.json()
            return ItemRef(
                project=project, id=str(task["id"]), number=task["index"], name=task["identifier"]
            )

        async def reply(ref: ItemRef, body: str) -> None:
            await client.put(
                f"{api}/tasks/{ref.id}/comments", json={"comment": body}, headers=headers
            )

        async def delete(ref: ItemRef) -> None:
            await client.delete(f"{api}/tasks/{ref.id}", headers=headers)

        yield Harness(
            tracker=VikunjaTracker(credentials(base, key), SOURCE, client=client),
            project=project,
            delivery=delivery,
            delivered=delivered,
            link=lambda ref: f"{base}/tasks/{ref.id}",
            add=add,
            reply=reply,
            delete=delete,
            archive=None,
            tick=tick,
        )
    if replayer is not None:
        assert replayer.done(), "the adapter asked for less than was recorded"
    elif RECORD:
        recording.save(fixture)


async def _idle() -> None:
    """No second need pass for a recording."""


async def _second() -> None:
    await asyncio.sleep(1.1)


async def _provision(url: str) -> tuple[str, int]:
    """A project of the test's own, for the run's user; return the user's API token and it."""
    async with httpx.AsyncClient(base_url=f"{url}/api/v1", timeout=10) as client:
        key = _USERS.get(url) or await _register(client)
        _USERS[url] = key
        client.headers["Authorization"] = f"Bearer {key}"
        identifier = f"OPS{secrets.token_hex(2).upper()}"
        project = await client.put("/projects", json={"title": "ops", "identifier": identifier})
        return key, project.raise_for_status().json()["id"]


async def _register(client: httpx.AsyncClient) -> str:
    """Register the run's user, and make its API token: once, as Vikunja limits registration."""
    name = f"relayr-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(16)
    user = {"username": name, "email": f"{name}@example.com", "password": password}
    (await client.post("/register", json=user)).raise_for_status()
    login = await client.post("/login", json={"username": name, "password": password})
    headers = {"Authorization": f"Bearer {login.raise_for_status().json()['token']}"}
    token = await client.put("/tokens", json=_TOKEN, headers=headers)
    return token.raise_for_status().json()["token"]


_USERS: dict[str, str] = {}
"""The run's user's API token, by Vikunja's URL."""


_TOKEN: dict[str, Any] = {
    "title": "relayr",
    "expires_at": "2099-01-01T00:00:00Z",
    "permissions": {
        "tasks": ["create", "read_one", "read_all", "update", "delete"],
        "projects": ["create"],
        "tasks_comments": ["create", "read_all"],
        "labels": ["create", "read_all"],
        "tasks_labels": ["create", "delete"],
    },
}
"""The scopes relayr's token needs (the tracker guide lists them), and `delete` on tasks and
`create` on projects for the test to act as a person."""


# ─── a live Plane ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _PlaneSession:
    """The run's Plane user: its API key, its web app session, and its workspace's slug."""

    key: str
    cookies: dict[str, str]
    csrf: str
    workspace: str


_PLANE_SESSIONS: dict[str, _PlaneSession] = {}
"""The run's user, by Plane's URL."""


class _Settling(Recorder):
    """Waits a second after each write: Plane's worker then touches the item's `updated_at`
    again, and a read straight after would find it changed once more."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        if request.method != "GET":
            await asyncio.sleep(1)
        return response


async def _plane_session(url: str) -> _PlaneSession:
    """Register the run's user in Plane's web app, with a workspace and an API key.

    Plane makes users, workspaces and keys only through its web app's session API, so this signs
    up as a browser does: a form with a CSRF token, then JSON with it in a header. A Plane never
    set up gets an instance admin first, as its first visitor would make one.
    """
    async with httpx.AsyncClient(base_url=url, timeout=30) as client:
        instance = (await client.get("/api/instances/")).raise_for_status().json()["instance"]
        if not instance["is_setup_done"]:
            admin = {"first_name": "relayr", "is_telemetry_enabled": "False"}
            await _plane_form(client, "/api/instances/admins/sign-up/", admin)
            client.cookies.clear()
        await _plane_form(client, "/auth/sign-up/", {})
        # `acme`, the recorded delivery's, if it is free, as on a new Plane.
        free = await client.get("/api/workspace-slug-check/", params={"slug": "acme"})
        workspace = "acme" if free.json()["status"] else f"acme-{secrets.token_hex(4)}"
        made = await _plane_post(client, "/api/workspaces/", {"name": "acme", "slug": workspace})
        made.raise_for_status()
        token = await _plane_post(client, "/api/users/api-tokens/", {"label": "relayr"})
        return _PlaneSession(
            key=token.raise_for_status().json()["token"],
            cookies=dict(client.cookies),
            csrf=await _plane_csrf(client),
            workspace=workspace,
        )


async def _plane_project(url: str, session: _PlaneSession) -> dict[str, Any]:
    """A project of the test's own, in the run's workspace: the recording's setup."""
    identifier = f"OPS{secrets.token_hex(2).upper()}"
    async with httpx.AsyncClient(timeout=30) as client:
        made = await client.post(
            f"{url}/api/v1/workspaces/{session.workspace}/projects/",
            json={"name": f"ops {identifier}", "identifier": identifier},
            headers={"X-Api-Key": session.key},
        )
    project = made.raise_for_status().json()["id"]
    return {"workspace": session.workspace, "project": project, "identifier": identifier}


def _plane_archive(
    url: str, session: _PlaneSession, workspace: str, project: str, item: str
) -> None:
    """Mark a work item done and archive it, which only Plane's web app does."""
    projects = f"{url}/api/v1/workspaces/{workspace}/projects/{project}"
    with httpx.Client(timeout=30, headers={"X-Api-Key": session.key}) as client:
        states = client.get(f"{projects}/states/").raise_for_status().json()["results"]
        done = next(state["id"] for state in states if state["group"] == "completed")
        client.patch(f"{projects}/work-items/{item}/", json={"state": done}).raise_for_status()
    with httpx.Client(timeout=30, cookies=session.cookies) as client:
        client.post(
            f"{url}/api/workspaces/{workspace}/projects/{project}/issues/{item}/archive/",
            headers={"X-CSRFToken": session.csrf},
        ).raise_for_status()


async def _plane_csrf(client: httpx.AsyncClient) -> str:
    return (await client.get("/auth/get-csrf-token/")).json()["csrf_token"]


async def _plane_form(client: httpx.AsyncClient, path: str, fields: dict[str, str]) -> None:
    """Post a sign-up form, as a new user `relayr-<hex>`; Plane answers each with a redirect,
    which names its error if it failed."""
    name = f"relayr-{secrets.token_hex(4)}"
    token = await _plane_csrf(client)
    signed_up = await client.post(
        path,
        data={
            "csrfmiddlewaretoken": token,
            "email": f"{name}@example.com",
            "password": secrets.token_urlsafe(18),
            **fields,
        },
        headers={"X-CSRFToken": token},
    )
    assert "error_code" not in signed_up.headers.get("location", ""), signed_up.headers


async def _plane_post(client: httpx.AsyncClient, path: str, body: Any) -> httpx.Response:
    return await client.post(path, json=body, headers={"X-CSRFToken": await _plane_csrf(client)})


def _addressed(hook: dict[str, Any], workspace: str) -> Delivery:
    """Plane's recorded delivery, as it signed it; or, to a run's workspace other than the one
    it was recorded in, re-addressed and signed again with `SECRET`, as Plane would."""
    body = hook["body"].encode()
    payload = json.loads(body)
    if payload["workspace_slug"] == workspace:
        return hook["headers"], body
    payload["workspace_slug"] = workspace
    body = json.dumps(payload).encode()
    return {**hook["headers"], **signed(body, "X-Plane-Signature")[0]}, body
