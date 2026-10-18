"""The tracker connector's reads: what runs filed, with its links and chains, and how the
follower is doing, each as reflexr's `authorize` allows, and each in its own tenant alone."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import HTTPConnection

import reflexr
import reflexr.workspace as r
from reflexr.core import Actor, TenantId
from reflexr.fastapi import Unauthorized
from relayr.fastapi import tracker_reads_router
from relayr.ledger import Ledger, TrackerDeadLetter, WorkspaceKey
from relayr.trackers import LOOP_CAP, LOOP_WINDOW, ItemDraft, ItemFields, Trackers
from relayr.trackers.events import TRACKED
from tests.app_types import Deployed
from tests.clock import START, FakeClock
from tests.trackers.conftest import CREDENTIALS, KEY, PROJECT, TENANT
from tests.trackers.following import Following, following

ITEMS = f"/relayr/v1/workspaces/{KEY.workspace_id}/tracker/items"
FOLLOWING = f"/relayr/v1/workspaces/{KEY.workspace_id}/tracker"


@dataclass
class Callers:
    """Who the requests are by, and what reflexr's `authorize` refuses them."""

    tenant: str | None = TENANT
    """The tenant `resolve_actor` names; None refuses the request."""

    refused: set[str] = field(default_factory=set[str])
    asked: list[tuple[str, str | None, str]] = field(
        default_factory=list[tuple[str, str | None, str]]
    )

    async def resolve(self, _connection: HTTPConnection) -> tuple[TenantId, Actor]:
        if self.tenant is None:
            raise Unauthorized("sign in")
        return self.tenant, reflexr.UserActor(id="alice")

    async def authorize(
        self, tenant: str, workspace: str | None, _actor: Actor, access: r.Access
    ) -> bool:
        self.asked.append((tenant, workspace, access.action))
        return access.action not in self.refused


@pytest.fixture
def callers() -> Callers:
    return Callers()


@pytest.fixture
def made(ledger: Ledger, clock: FakeClock) -> Following:
    return following(ledger, clock)


def server(trackers: Trackers, made: Following, callers: Callers) -> FastAPI:
    workspaces = r.Workspaces(
        made.storage, events=(Deployed, *TRACKED), clock=made.clock, authorize=callers.authorize
    )
    app = FastAPI()
    app.include_router(tracker_reads_router(trackers, workspaces, resolve_actor=callers.resolve))
    return app


@pytest.fixture
async def client(made: Following, callers: Callers) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=server(made.trackers, made, callers))
    async with httpx.AsyncClient(transport=transport, base_url="http://relayr.test") as made_:
        yield made_


async def _chain(made: Following) -> str:
    """The chain of the last run the harness made."""
    handle = await made.workspaces.open(*KEY, actor=reflexr.SystemActor())
    return max(await handle.runs(), key=lambda run: run.fired_seq).correlation_id


async def test_the_items_runs_filed_have_their_links_and_chains(
    made: Following, client: httpx.AsyncClient
) -> None:
    first = await made.filed("dead-letter/a", "a fails")
    filing = await _chain(made)
    second = await made.filed("dead-letter/b", "b fails")
    other = await _chain(made)
    commenting = await made.acting()
    await commenting.comment(first, "<p>again</p>")
    again = await _chain(made)
    await (await made.acting()).comment(first, "<p>and again</p>", key="same")
    made.tracker.delete(second)
    await (await made.acting()).ensure_item(ItemDraft(title="b fails"), key="dead-letter/b")
    answer = (await client.get(ITEMS)).json()
    link = f"{CREDENTIALS.base_url}/{PROJECT}"
    assert answer["tracker"] == "fake"
    assert [item["name"] for item in answer["items"]] == [second.name, first.name], "newest first"
    newest, oldest = answer["items"]
    assert newest == {
        "key": "dead-letter/b",
        "project": PROJECT,
        "id": second.id,
        "number": second.number,
        "name": second.name,
        "link": f"{link}/{second.number}",
        "deleted": True,
        "chains": [other],
    }
    assert oldest["link"] == f"{link}/{first.number}"
    assert oldest["chains"][:2] == [filing, again], "its filing chain first, then its comments'"
    assert len(oldest["chains"]) == 3


async def test_a_workspace_bound_to_nothing_now_has_no_links(
    made: Following, callers: Callers
) -> None:
    await made.filed("dead-letter/a")
    unbound = following(made.ledger, made.clock, bindings={})
    transport = httpx.ASGITransport(app=server(unbound.trackers, made, callers))
    async with httpx.AsyncClient(transport=transport, base_url="http://relayr.test") as client:
        [item] = (await client.get(ITEMS)).json()["items"]
        following_ = (await client.get(FOLLOWING)).json()
    assert item["link"] is None
    assert following_["binding"] is None
    assert made.tenant.asked == [TENANT], "nothing asks for the credentials of no binding"


async def test_how_the_follower_is_doing(
    made: Following, client: httpx.AsyncClient, clock: FakeClock
) -> None:
    before = (await client.get(FOLLOWING)).json()
    assert before["reading"] is None
    assert (before["filed"], before["dead_letters"], before["writes"]) == (0, [], [])
    item = await made.filed("dead-letter/a")
    await (await made.acting()).set_state(item, "done")  # a write the cap counts; filing isn't
    made.tracker.edit(item, ItemFields(title="renamed"))
    assert await made.poll()
    letter = TrackerDeadLetter(
        event_id="trk_1", event_type="tracker:item_changed", item_id=item.id, error="ValueError: no"
    )
    await made.ledger.tracker_dead_letter(KEY, letter)
    answer = (await client.get(FOLLOWING)).json()
    assert answer["tracker"] == "fake"
    assert answer["integration"] == "tracker:fake"
    assert answer["binding"]["project"] == PROJECT
    assert answer["reading"]["project"] == PROJECT
    assert answer["reading"]["read_at"] == START.isoformat().replace("+00:00", "Z")
    assert answer["filed"] == 1
    assert answer["dead_letters"] == [letter.model_dump()]
    assert answer["writes"] == [
        {
            "item_id": item.id,
            "name": item.name,
            "link": f"{CREDENTIALS.base_url}/{PROJECT}/{item.number}",
            "writes": 1,
        }
    ]
    assert (answer["loop_cap"], answer["loop_window_seconds"]) == (LOOP_CAP, 3600)


async def test_an_item_written_to_but_never_read_has_no_name(
    made: Following, client: httpx.AsyncClient
) -> None:
    for _ in range(2):
        await made.ledger.record_tracker_write(KEY, "9", within=LOOP_WINDOW)
    [written] = (await client.get(FOLLOWING)).json()["writes"]
    assert written == {"item_id": "9", "name": None, "link": None, "writes": 2}


async def test_each_read_asks_authorize_about_its_workspace(
    made: Following, client: httpx.AsyncClient, callers: Callers
) -> None:
    await client.get(ITEMS)
    await client.get(FOLLOWING)
    workspace = KEY.workspace_id
    assert callers.asked == [
        (TENANT, workspace, "reflexr:open"),
        (TENANT, workspace, "reflexr:read_runs"),
        (TENANT, workspace, "reflexr:open"),
        (TENANT, workspace, "reflexr:read_dead_letters"),
    ]


@pytest.mark.parametrize(
    ("refused", "path"),
    [
        ("reflexr:open", ITEMS),
        ("reflexr:read_runs", ITEMS),
        ("reflexr:read_dead_letters", FOLLOWING),
    ],
)
async def test_a_read_authorize_refuses_is_forbidden(
    client: httpx.AsyncClient, callers: Callers, refused: str, path: str
) -> None:
    callers.refused.add(refused)
    answer = await client.get(path)
    assert answer.status_code == 403
    assert answer.json() == {"detail": f"{refused} is refused in this workspace"}


async def test_a_workspace_reflexr_refuses_is_refused_as_reflexr_refuses_it(
    client: httpx.AsyncClient,
) -> None:
    answer = await client.get("/relayr/v1/workspaces/a%00b/tracker/items")
    assert answer.status_code == 422
    assert "detail" in answer.json()


async def test_an_adapter_already_made_links_without_asking_for_credentials(
    made: Following, client: httpx.AsyncClient
) -> None:
    await made.filed("dead-letter/a")
    assert await made.poll()
    asked = len(made.tenant.asked)
    [item] = (await client.get(ITEMS)).json()["items"]
    assert item["link"] is not None
    assert len(made.tenant.asked) == asked


async def test_a_caller_resolve_actor_refuses_is_unauthorized(
    client: httpx.AsyncClient, callers: Callers
) -> None:
    callers.tenant = None
    for path in (ITEMS, FOLLOWING):
        answer = await client.get(path)
        assert (answer.status_code, answer.json()) == (401, {"detail": "sign in"})
    assert callers.asked == []


async def test_another_tenant_reads_only_its_own(
    made: Following, client: httpx.AsyncClient, callers: Callers
) -> None:
    await made.filed("dead-letter/a")
    assert await made.poll()
    callers.tenant = "globex"
    assert (await client.get(ITEMS)).json() == {"tracker": "fake", "items": []}
    other = (await client.get(FOLLOWING)).json()
    assert (other["binding"], other["reading"], other["filed"]) == (None, None, 0)
    assert WorkspaceKey("globex", KEY.workspace_id) not in made.trackers.bindings
