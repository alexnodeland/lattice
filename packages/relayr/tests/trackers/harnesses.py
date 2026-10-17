"""The trackers the contract test runs against, each with what a test does in it as a person.

- `fake`: relayr's `FakeTracker`.
- `vikunja`: Vikunja's recorded exchanges, replayed; or, with `RELAYR_TEST_VIKUNJA_URL` set, a
  live Vikunja, recorded (and saved as the fixtures with `RELAYR_RECORD=1`). A live run registers
  a user of its own, with an API token, and each test makes a project: the instance must allow
  registration, as `moon run relayr:vikunja-up` starts it.
- `plane`: `PlaneApi`, Plane's API as its v1.4.2 source reads (`tests/trackers/plane_api.py`):
  no Plane runs on a pull request or here, so its exchanges are not recorded but derived.
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
from tests.trackers.plane_api import PlaneApi
from tests.trackers.recorded import FIXTURES, Recorder, Recording, Replayer

SOURCE = "lattice:acme/ops"
SECRET = "whsec-test"
VIKUNJA_URL = os.environ.get("RELAYR_TEST_VIKUNJA_URL")
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
async def plane() -> AsyncIterator[Harness]:
    api = PlaneApi(secret=SECRET)

    async def add(title: str) -> ItemRef:
        return api.add(title)

    async def reply(ref: ItemRef, body: str) -> None:
        api.reply(ref, body)

    async def delete(ref: ItemRef) -> None:
        api.delete(ref)

    async with httpx.AsyncClient(transport=httpx.MockTransport(api.handle)) as client:
        yield Harness(
            tracker=PlaneTracker(credentials(PlaneApi.URL), SOURCE, client=client),
            project=api.project,
            delivery=api.delivery(),
            delivered=api.project,
            link=lambda ref: f"{PlaneApi.URL}/acme/browse/{ref.name}/",
            add=add,
            reply=reply,
            delete=delete,
            archive=api.archive,
        )


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
