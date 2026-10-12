"""portalr's test application, for its acceptance tests only: the router over the stack's tools.

It mounts ``portalr_router``, grantr's own router for the UIs' ``/me`` and ``/checks``, and
artifactr's, with a scripted agent (``notes.py``), over grantr's ``Grants`` in memory, which checks
every artifactr command and read; it invites without Supabase. acme's owner is alice, and bob is its
member with no tenant role, an editor of its workspaces ``notes`` and ``plans``; globex's owner is
carol; erin is a member of both, and edits acme's ``notes``; ops is the deployment's operator.

A caller is named by a Supabase Auth access token, verified as the template verifies one, or by
the ``x-user`` header, which the API tests send. Signed in, a person's user id here is their
email's local part, so the seed needn't know the ids Supabase Auth gives them. Supabase Auth
itself (GoTrue, alone) answers at ``/auth/v1`` on this origin, as it does behind Supabase's
gateway, so ``config.json`` names this origin for it (portalr ADR-0013).

Each tool is read at the URL its environment variable names; Langfuse and LiteLLM aren't in its
compose, so their reads are unavailable (portalr ADR-0011). Phase 7 moves the UIs' scenarios to an
application the template generates, and this application's wiring of grantr goes then.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.requests import HTTPConnection

import artifactr
import artifactr.core
import artifactr.fastapi
import reflexr
import reflexr.core
import reflexr.fastapi
from artifactr.workspace import ACTIONS as ARTIFACTR_ACTIONS
from grantr.core import Resource, User
from grantr.fastapi import Caller, Unauthorized, grantr_router
from grantr.grants import Grants, InMemoryStorage
from portalr.actions import ACTIONS
from portalr.fastapi import UI, Site, portalr_router
from portalr.readers import Grafana, Langfuse, LiteLLM, Loki, Prometheus, Readers, Tempo
from reflexr.workspace import ACTIONS as REFLEXR_ACTIONS
from tests.app.notes import APPLICATION, collaboration
from tests.app.tickets import automation

OPS, ALICE, BOB, CAROL, ERIN, VERA = (
    User(id=name) for name in ("ops", "alice", "bob", "carol", "erin", "vera")
)

PEOPLE = "portalr.test"
"""The domain of the people the scenarios sign up: no one else's email names a user here."""

FORWARDED: tuple[str, ...] = ("content-type", "cache-control")
"""The headers of Supabase Auth's answers the application passes on."""


def workspace(name: str) -> Resource:
    """A workspace, as grantr names one."""
    return Resource(kind="workspace", workspace=name)


async def seed(grants: Grants) -> None:
    """Two tenants, their owners, members with and without workspaces, a viewer, and the
    operator."""
    await grants.first_operator(OPS.id)
    await grants.create_tenant("acme", owner=ALICE.id, by=OPS)
    await grants.create_tenant("globex", owner=CAROL.id, by=OPS)
    for member in (BOB, ERIN, VERA):
        await grants.add_member("acme", member, by=ALICE)
    await grants.add_member("globex", ERIN, by=CAROL)
    for name in ("notes", "plans"):
        await grants.grant("acme", "editor", on=workspace(name), to=BOB, by=ALICE)
    await grants.grant("acme", "editor", on=workspace("notes"), to=ERIN, by=ALICE)
    await grants.grant("acme", "viewer", on=workspace("notes"), to=VERA, by=ALICE)


def signed_in(token: str) -> User:
    """The user a Supabase Auth access token names, by its email's local part.

    Raises:
        Unauthorized: If the token isn't signed with the project's secret, has expired, is for
            another audience, or names someone outside the scenarios' domain.
    """
    try:
        claims = jwt.decode(
            token,
            os.environ["PORTALR_JWT_SECRET"],
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub", "aud", "email"]},
        )
    except (KeyError, jwt.InvalidTokenError) as error:
        raise Unauthorized("the access token is not valid") from error
    user, _, domain = str(claims["email"]).partition("@")
    if domain != PEOPLE:
        raise Unauthorized(f"only the scenarios' people sign in here, at {PEOPLE}")
    return User(id=user)


def person(connection: HTTPConnection) -> User:
    """Who a request names: by a bearer token, in the query on a stream, which a browser opens
    without headers; or else by the ``x-user`` header, as docplan trusts it.

    Raises:
        Unauthorized: If it names no one, or with a token that isn't valid.
    """
    scheme, _, token = connection.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" and connection.scope["type"] == "websocket":
        token = connection.query_params.get("access_token", "")
        scheme = "bearer"
    if scheme.lower() == "bearer" and token:
        return signed_in(token)
    if user := connection.headers.get("x-user"):
        return User(id=user)
    raise Unauthorized("sign in")


async def resolve_actor(connection: HTTPConnection) -> Caller:
    """The caller, to grantr's router and portalr's."""
    return Caller(person(connection))


def library_actor[A](
    grants: Grants,
    actor: Callable[[str], A],
    unauthorized: Callable[[str], Exception],
    forbidden: Callable[[str], Exception],
) -> Callable[[HTTPConnection], Awaitable[tuple[str, A]]]:
    """A library's caller: the person, a member of the tenant ``X-Tenant`` names, or a stream's
    ``tenant``, as the template resolves one, with the library's own refusals."""

    async def resolve(connection: HTTPConnection) -> tuple[str, A]:
        try:
            user = person(connection)
        except Unauthorized as error:
            raise unauthorized(str(error)) from error
        tenant = connection.headers.get("x-tenant") or connection.query_params.get("tenant")
        if not tenant:
            raise HTTPException(
                status_code=400, detail="name the tenant with X-Tenant, or a stream's ?tenant="
            )
        if await grants.member(tenant, user.id) is None:
            raise forbidden(f"{user.id} isn't a member of {tenant}")
        return tenant, actor(user.id)

    return resolve


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
    grants = Grants(
        InMemoryStorage(),
        catalogs=[ACTIONS, ARTIFACTR_ACTIONS, REFLEXR_ACTIONS],
        application=APPLICATION,
    )
    workspaces, runner = collaboration(grants)
    tickets, reactor = automation(grants, APPLICATION)
    gotrue = os.environ.get("PORTALR_GOTRUE_URL", "http://gotrue:9999")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await grants.bootstrap()
        await seed(grants)
        stop = asyncio.Event()
        reacting = asyncio.create_task(
            reactor.serve(poll_interval=timedelta(milliseconds=200), stop=stop)
        )
        async with httpx.AsyncClient(base_url=gotrue) as auth:
            app.state.auth = auth
            try:
                yield
            finally:
                stop.set()
                await reacting
                await runner.aclose()

    app = FastAPI(title="portalr's test application", lifespan=lifespan)
    app.include_router(grantr_router(grants, resolve_actor=resolve_actor), prefix="/grantr/v1")
    app.include_router(
        artifactr.fastapi.artifactr_router(
            workspaces,
            runner,
            resolve_actor=library_actor(
                grants,
                lambda user: artifactr.UserActor(id=user, name=user),
                artifactr.fastapi.Unauthorized,
                artifactr.core.Forbidden,
            ),
        ),
        prefix="/artifactr/v1",
    )
    app.include_router(
        reflexr.fastapi.reflexr_router(
            tickets,
            resolve_actor=library_actor(
                grants,
                lambda user: reflexr.UserActor(id=user, name=user),
                reflexr.fastapi.Unauthorized,
                reflexr.core.Forbidden,
            ),
        ),
        prefix="/reflexr/v1",
    )
    app.include_router(
        portalr_router(
            resolve_actor=resolve_actor,
            grants=grants,
            readers=readers(),
            invite=invite,
            site=Site(supabase_url="/", supabase_key="sb_publishable_test"),
            ui=ui,
        ),
        prefix="/portalr",
    )

    @app.api_route(
        "/auth/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False
    )
    async def supabase_auth(path: str, request: Request) -> Response:
        """Supabase Auth, as Supabase's gateway serves it: GoTrue, at ``/auth/v1``."""
        auth: httpx.AsyncClient = request.app.state.auth
        answer = await auth.request(
            request.method,
            f"/{path}",
            params=request.query_params,
            headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
            content=await request.body(),
        )
        kept = {k: v for k, v in answer.headers.items() if k.lower() in FORWARDED}
        return Response(answer.content, status_code=answer.status_code, headers=kept)

    return app


app = create_app()
