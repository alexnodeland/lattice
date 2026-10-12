"""An application that mounts the router, with header-based callers, over in-memory grants."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr.core import User
from grantr.fastapi import Caller, Unauthorized, grantr_router
from grantr.grants import Grants, InMemoryStorage
from tests.catalogs import ARTIFACTR

ROOT = User(id="root")
ALICE = User(id="alice")


def app_for(grants: Grants) -> FastAPI:
    """An application whose callers are named by ``X-User``, or by a key in ``X-Api-Key``."""

    async def resolve_actor(connection: HTTPConnection) -> Caller:
        if key := connection.headers.get("x-api-key"):
            if (found := await grants.authenticate(key)) is None:
                raise Unauthorized("unknown key")
            tenant, principal = found
            return Caller(principal, tenant)
        if user := connection.headers.get("x-user"):
            return Caller(User(id=user))
        raise Unauthorized

    app = FastAPI()
    app.include_router(grantr_router(grants, resolve_actor=resolve_actor), prefix="/grantr/v1")
    return app


@pytest.fixture
async def grants() -> Grants:
    grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR])
    await grants.first_operator(ROOT.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)
    return grants


@pytest.fixture
async def client(grants: Grants) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app_for(grants))
    async with httpx.AsyncClient(transport=transport, base_url="http://grantr/grantr/v1") as client:
        yield client
