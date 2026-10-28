"""An application that mounts portalr's router, with callers named by ``X-User``.

acme's owner is alice, and bob is its member with no role; globex's owner is carol; ops is the
deployment's operator. Every tool is a stand-in whose answers a test scripts.
"""

from collections.abc import AsyncIterator, Collection
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr.core import ServicePrincipal, User
from grantr.fastapi import Caller, Unauthorized
from grantr.grants import Grants, InMemoryStorage
from portalr.actions import ACTIONS
from portalr.analytics import Relay
from portalr.fastapi import Site, portalr_router
from portalr.invites import Invite
from portalr.models import Models
from portalr.people import People
from portalr.readers import Grafana, Langfuse, LiteLLM, Loki, Prometheus, Readers, Tempo
from tests.tools import Tool

OPS, ALICE, BOB, CAROL = (User(id=name) for name in ("ops", "alice", "bob", "carol"))
SITE = Site(supabase_url="https://project.supabase.co", supabase_key="sb_publishable_x")


@dataclass
class Stack:
    """The stand-ins for the stack's tools."""

    tempo: Tool
    loki: Tool
    prometheus: Tool
    langfuse: Tool
    litellm: Tool

    def readers(self) -> Readers:
        return Readers(
            tempo=Tempo("http://tempo", self.tempo.client()),
            loki=Loki("http://loki", self.loki.client()),
            prometheus=Prometheus("http://proxy", self.prometheus.client()),
            langfuse=Langfuse("http://langfuse", project="p1", client=self.langfuse.client()),
            litellm=LiteLLM("http://litellm", self.litellm.client()),
            grafana=Grafana("http://grafana"),
        )


async def seeded[G: Grants](kind: type[G]) -> G:
    """grantr's grants, in memory, with portalr's catalog, the two tenants and their people."""
    grants = kind(InMemoryStorage(), catalogs=[ACTIONS])
    await grants.first_operator(OPS.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=OPS)
    await grants.create_tenant("globex", owner=CAROL.id, by=OPS)
    await grants.add_member("acme", BOB, by=ALICE)
    return grants


@pytest.fixture
async def grants() -> Grants:
    return await seeded(Grants)


@pytest.fixture
def stack() -> Stack:
    return Stack(Tool(), Tool(), Tool(), Tool(), Tool())


@pytest.fixture
def ui(tmp_path: Path) -> Path:
    (tmp_path / "app" / "assets").mkdir(parents=True)
    (tmp_path / "app" / "index.html").write_text("<!doctype html><title>app</title>")
    (tmp_path / "app" / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "secret.txt").write_text("outside the UI")
    return tmp_path


@pytest.fixture
def invited() -> list[str]:
    return []


@pytest.fixture
def invite(invited: list[str]) -> Invite:
    async def invite(email: str) -> str:
        invited.append(email)
        return email.partition("@")[0]

    return invite


EMAILS = {
    "alice": "alice@acme.test",
    "bob": "bob@acme.test",
    "carol": "carol@globex.test",
    "ops": "ops@deployment.test",
    "noemail": "",
}
"""Auth's emails by user id: one user has none."""


class Directory:
    """The people hook's stand-in: it answers from ``EMAILS`` and keeps the ids it was asked."""

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    async def __call__(self, ids: Collection[str]) -> dict[str, str]:
        self.asked.append(list(ids))
        return {each: EMAILS[each] for each in ids if EMAILS.get(each)}


@pytest.fixture
def directory() -> Directory:
    return Directory()


@pytest.fixture
def people(directory: Directory) -> People:
    return directory


async def resolve_actor(connection: HTTPConnection) -> Caller:
    """A caller named by ``X-User``, bound to one tenant if ``X-Key-Tenant`` says, as a key is."""
    if principal := connection.headers.get("x-principal"):
        return Caller(ServicePrincipal(id=principal), connection.headers.get("x-key-tenant"))
    if user := connection.headers.get("x-user"):
        return Caller(User(id=user), connection.headers.get("x-key-tenant"))
    raise Unauthorized


def app_for(
    grants: Grants,
    readers: Readers,
    invite: Invite | None,
    ui: Path,
    people: People | None = None,
    site: Site = SITE,
    relay: Relay | None = None,
    models: Models | None = None,
) -> FastAPI:
    app = FastAPI()
    router = portalr_router(
        resolve_actor=resolve_actor,
        grants=grants,
        readers=readers,
        invite=invite,
        site=site,
        ui=ui,
        people=people,
        relay=relay,
        models=models,
    )
    app.include_router(router, prefix="/portalr")
    return app


@pytest.fixture
async def client(
    grants: Grants, stack: Stack, invite: Invite, ui: Path
) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app_for(grants, stack.readers(), invite, ui))
    async with httpx.AsyncClient(transport=transport, base_url="http://app/portalr") as client:
        yield client


@pytest.fixture
async def naming_client(
    grants: Grants, stack: Stack, invite: Invite, ui: Path, people: People
) -> AsyncIterator[httpx.AsyncClient]:
    """The same application, with a people hook."""
    app = app_for(grants, stack.readers(), invite, ui, people)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        yield client
