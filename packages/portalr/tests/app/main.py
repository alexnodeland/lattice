"""portalr's test application, for its acceptance tests only: the router over the stack's tools.

It mounts ``portalr_router`` with grantr's ``Grants`` in memory, trusts the ``x-user`` header as
docplan does, and invites without Supabase. acme's owner is alice, and bob is its member with no
role; globex's owner is carol; ops is the deployment's operator. Each tool is read at the URL its
environment variable names; Langfuse and LiteLLM aren't in its compose, so their reads are
unavailable (portalr ADR-0011).
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr.core import User
from grantr.fastapi import Caller, Unauthorized
from grantr.grants import Grants, InMemoryStorage
from portalr.actions import ACTIONS
from portalr.fastapi import UI, Site, portalr_router
from portalr.readers import Grafana, Langfuse, LiteLLM, Loki, Prometheus, Readers, Tempo

OPS, ALICE, BOB, CAROL = (User(id=name) for name in ("ops", "alice", "bob", "carol"))


async def seed(grants: Grants) -> None:
    """Two tenants, their owners, a member with no role, and the operator."""
    await grants.first_operator(OPS.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=OPS)
    await grants.create_tenant("globex", owner=CAROL.id, by=OPS)
    await grants.add_member("acme", BOB, by=ALICE)


async def resolve_actor(connection: HTTPConnection) -> Caller:
    """The caller the ``x-user`` header names: a test application's trust, as docplan's."""
    if user := connection.headers.get("x-user"):
        return Caller(User(id=user))
    raise Unauthorized


async def invite(email: str) -> str:
    """Invite without Supabase: the user's id is the email's local part."""
    return email.partition("@")[0]


def readers() -> Readers:
    """The tools, at the URLs the environment names."""
    env = os.environ.get
    return Readers(
        tempo=Tempo(env("PORTALR_TEMPO_URL", "http://tempo:3200")),
        loki=Loki(env("PORTALR_LOKI_URL", "http://loki:3100")),
        prometheus=Prometheus(env("PORTALR_PROXY_URL", "http://prom-label-proxy:8080")),
        langfuse=Langfuse(env("PORTALR_LANGFUSE_URL", "http://langfuse:3000"), project="p1"),
        litellm=LiteLLM(env("PORTALR_LITELLM_URL", "http://litellm:4000")),
        grafana=Grafana("http://localhost:3000"),
    )


def create_app(ui: Path = UI) -> FastAPI:
    """The test application."""
    grants = Grants(InMemoryStorage(), catalogs=[ACTIONS])

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await seed(grants)
        yield

    app = FastAPI(title="portalr's test application", lifespan=lifespan)
    app.include_router(
        portalr_router(
            resolve_actor=resolve_actor,
            grants=grants,
            readers=readers(),
            invite=invite,
            site=Site(supabase_url="http://localhost:54321", supabase_key="sb_publishable_test"),
            ui=ui,
        ),
        prefix="/portalr",
    )
    return app


app = create_app()
