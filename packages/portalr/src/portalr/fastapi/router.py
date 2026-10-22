"""portalr's router: the two UIs, their ``config.json``, and the routes no library has.

An application mounts it at ``/portalr``, beside the libraries' routers. The browser calls each
library's own routes; portalr adds only reading the stack's tools for one tenant, inviting users,
and, for operators, the deployment's tenants and deep links (lattice RFC-0002).
"""

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Final

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from grantr.core import (
    DEPLOYMENT,
    TENANT,
    Forbidden,
    GrantrError,
    Invalid,
    Subject,
    TenantId,
    User,
)
from grantr.fastapi import STATUS_CODES, Caller, ResolveActor, Unauthorized
from grantr.grants import Grants
from lattice_core.refusals import Refused, refusals
from portalr.access import record_links
from portalr.actions import READ_DEPLOYMENT, READ_SPEND, READ_TELEMETRY
from portalr.analytics.relay import (
    MOST_BYTES,
    Answer,
    Answered,
    Batch,
    Relay,
    Relayed,
    Session,
    kept,
)
from portalr.fastapi.site import Site, Surfaces
from portalr.fastapi.ui import ui_router
from portalr.invites import Invite, InviteFailed
from portalr.people import People
from portalr.readers import (
    Feedback,
    FeedbackQuery,
    LogQuery,
    LogRecord,
    Logs,
    MetricQuery,
    Ok,
    Point,
    Readers,
    Scores,
    Spend,
    TenantSpend,
    Trace,
    TraceQuery,
    TraceSummary,
    Unavailable,
    Unconfigured,
    Usage,
    UsageQuery,
    Window,
    read_feedback,
    read_usage,
    reading,
)
from portalr.readers.analytics import REGISTRY, Analytics, actor_of
from portalr.readers.loki import RECORD_ID
from portalr.readers.query import Id
from portalr.tenant import Tenant, allowed

UI: Final = Path(str(files("portalr") / "static"))
"""Where portalr's wheel carries the built UIs: ``static/app`` and ``static/admin``."""


class Supabase(BaseModel):
    """The Supabase project the UIs sign in to."""

    model_config = ConfigDict(frozen=True)

    url: str
    """Its URL, or a path on the application's own origin."""
    key: str
    """Its publishable key."""


class BrandMarks(BaseModel):
    """A kit's header mark, in each scheme, by its path under the portal's mount."""

    model_config = ConfigDict(frozen=True)

    light: str
    dark: str


class BrandIdentity(BaseModel):
    """What the product is called: in the tab, the app's header, and admin's."""

    model_config = ConfigDict(frozen=True)

    product: str
    app: str
    admin: str


class BrandCopy(BaseModel):
    """The words a kit sets; each absent where the kit leaves portalr's."""

    model_config = ConfigDict(frozen=True)

    tagline: str | None = None
    sign_in: str | None = Field(default=None, alias="signIn")


class Brand(BaseModel):
    """The deployment's brand kit, as the UIs read it (lattice RFC-0007).

    Who it is, and where its stylesheet and marks are, each under a hash of the kit, relative to
    the portal's mount.
    """

    model_config = ConfigDict(frozen=True)

    hash: str
    identity: BrandIdentity
    copy_: BrandCopy = Field(alias="copy", serialization_alias="copy")
    stylesheet: str
    mark: BrandMarks
    favicon: str


class Config(BaseModel):
    """``config.json``: what the UIs need of the deployment they run in."""

    model_config = ConfigDict(frozen=True)

    supabase: Supabase
    surfaces: Surfaces
    readers: dict[str, bool]
    people: bool
    """Whether the router names people: whether the UIs may ask it for their emails."""
    editors: dict[str, str]
    """Each native file's hosted editor, by its app's integration."""
    apps: str | None
    """The origin mini apps run on, or None where the deployment runs none."""
    brand: Brand | None = None
    """The deployment's brand kit, or None for portalr's own look."""


class NewInvite(BaseModel):
    """Whom to invite to the tenant ``X-Tenant`` names."""

    model_config = ConfigDict(frozen=True)

    email: Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)]


class Invited(BaseModel):
    """The member an invitation made, by the user id their tokens carry."""

    model_config = ConfigDict(frozen=True)

    tenant: str
    user: str


EMAIL: Final = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
"""What an owner's email must look like: checked here by hand, so that a malformed one is refused
without being echoed back, as a model's validation error would."""

MOST_EMAIL: Final = 254


class NewTenant(BaseModel):
    """A tenant to create, and the email of its first owner."""

    model_config = ConfigDict(frozen=True)

    tenant: TenantId
    owner_email: str


class CreatedTenant(BaseModel):
    """The tenant a creation made, and its owner.

    The owner is by the user id their tokens carry, never by email.
    """

    model_config = ConfigDict(frozen=True)

    tenant: str
    owner: str


class Names(BaseModel):
    """The emails of the people asked after whom the caller may see, by user id.

    An id left out is one the caller may not see, one with no user, or one with no email, and the
    answer is the same for all three.
    """

    model_config = ConfigDict(frozen=True)

    people: dict[str, str]


class DeploymentTenants(BaseModel):
    """Every tenant, and their spend, as one LiteLLM team list reads it."""

    model_config = ConfigDict(frozen=True)

    tenants: list[str]
    spend: Annotated[
        Ok[list[TenantSpend]] | Unavailable | Unconfigured, Field(discriminator="status")
    ]


class Links(BaseModel):
    """Deep links into the stack's own tools, which only operators get."""

    model_config = ConfigDict(frozen=True)

    langfuse_trace: str | None = None
    langfuse_session: str | None = None
    langfuse_tenant: str | None = None
    grafana_trace: str | None = None
    grafana_logs: str | None = None
    grafana_tenant_logs: str | None = None
    grafana_tenant_traces: str | None = None


REFUSALS: Final = refusals(400, 401, 403, 422)
"""The refused responses every route under ``/v1`` documents: no route of portalr's answers 404 or
409, which artifactr's and reflexr's document."""


TenantHeader = Annotated[TenantId | None, Header(alias="X-Tenant")]
"""The tenant a request reads, which grantr checks."""

DEPLOYMENT_CHECK: Final = "deployment"
"""The tenant a deployment-wide check names: grantr reads none of its grants for one."""


def _refusal(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=STATUS_CODES[code], detail={"type": code, "message": message})


def portalr_router(
    *,
    resolve_actor: ResolveActor,
    grants: Grants,
    readers: Readers,
    invite: Invite | None,
    site: Site,
    ui: Path = UI,
    people: People | None = None,
    relay: Relay | None = None,
) -> APIRouter:
    """Build portalr's router, for an application to mount at ``/portalr``.

    Args:
        resolve_actor: Authenticates each request, as grantr's router does.
        grants: What decides each read, and adds invited members.
        readers: The stack's tools, each optional.
        invite: Supabase Auth's admin API, from the application's settings; without it,
            there is no invitation route.
        site: The application's Supabase project and surfaces, for ``config.json``.
        ui: Where the built UIs are; the wheel's own, unless a test says otherwise.
        people: Names people by email, from the application's auth service; without it, the UIs
            show a short id, and there is no people route.
        relay: Product analytics from people's browsers, with their consent (lattice RFC-0008);
            without it, there are no analytics routes.
    """
    router = APIRouter()
    router.include_router(ui_router(site, ui))
    api = APIRouter(responses=REFUSALS)

    async def caller(request: Request) -> Caller:
        try:
            return await resolve_actor(request)
        except Unauthorized as error:
            raise _refusal("unauthorized", str(error) or "no caller") from error

    current = Depends(caller)

    def tenant_read(action: str) -> Callable[..., Awaitable[Tenant]]:
        async def tenant(x_tenant: TenantHeader = None, who: Caller = current) -> Tenant:
            named = x_tenant or who.tenant
            if named is None:
                raise _refusal("tenant_required", "name the tenant with X-Tenant")
            if who.tenant is not None and who.tenant != named:
                raise _refusal("forbidden", "this caller's key is for another tenant")
            if not await grants.check(named, who.subject, action, TENANT):
                raise _refusal("forbidden", f"the caller may not {action} in {named}")
            return allowed(named)

        return tenant

    telemetry = Depends(tenant_read(READ_TELEMETRY))
    spending = Depends(tenant_read(READ_SPEND))

    async def operator(who: Caller = current) -> Subject:
        if not await _operates(grants, who):
            raise _refusal("forbidden", f"the caller may not {READ_DEPLOYMENT}")
        return who.subject

    operating = Depends(operator)

    @router.get("/config.json")
    async def config() -> Config:
        """What the UIs need of this deployment: Supabase, the surfaces, and the tools it runs."""
        return Config(
            supabase=Supabase(url=site.supabase_url, key=site.supabase_key),
            surfaces=site.surfaces,
            readers=readers.configured(),
            people=people is not None,
            editors=site.editors,
            apps=site.apps,
            brand=Brand.model_validate(site.kit.config()) if site.kit else None,
        )

    @api.get("/v1/traces", response_model=reading(list[TraceSummary]))
    async def traces(
        query: Annotated[TraceQuery, Query()], tenant: Tenant = telemetry
    ) -> Ok[list[TraceSummary]] | Unavailable | Unconfigured:
        """The tenant's traces, a session's or a run's, from Tempo."""
        return await readers.tempo.search(tenant, query) if readers.tempo else Unconfigured()

    @api.get("/v1/traces/{trace_id}", response_model=reading(Trace | None))
    async def trace(
        trace_id: Id,
        response: Response,
        content: bool = False,
        span: Id | None = None,
        tenant: Tenant = telemetry,
    ) -> Ok[Trace | None] | Unavailable | Unconfigured:
        """A trace, if it is the tenant's: its spans, for its waterfall.

        Only the attributes known to be safe are shown. ``content=true`` and ``span`` ask for one
        span's others, its prompt and completion among them, and nothing of any other span's; the
        answer is not to be kept.
        """
        if content and span is None:
            raise HTTPException(422, "content is asked for a span: name it with span")
        if not readers.tempo:
            return Unconfigured()
        if content:
            response.headers["Cache-Control"] = "no-store"
        return await readers.tempo.trace(tenant, trace_id, reveal=span if content else None)

    @api.get("/v1/logs", response_model=reading(Logs))
    async def logs(
        query: Annotated[LogQuery, Query()], tenant: Tenant = telemetry
    ) -> Ok[Logs] | Unavailable | Unconfigured:
        """The tenant's logs, a thread's or a run's, from Loki, without their lines.

        A record has its time, level, service, thread, run and its line's length, and the labels
        known to be safe; the line and the other labels are withheld, and named.
        """
        return await readers.loki.logs(tenant, query) if readers.loki else Unconfigured()

    @api.get("/v1/logs/{record_id}", response_model=reading(LogRecord | None))
    async def log_line(
        record_id: Annotated[str, PathParam(pattern=RECORD_ID)],
        response: Response,
        tenant: Tenant = telemetry,
    ) -> Ok[LogRecord | None] | Unavailable | Unconfigured:
        """One of the tenant's log records by its id, with its line: asked for, and not kept."""
        if not readers.loki:
            return Unconfigured()
        response.headers["Cache-Control"] = "no-store"
        return await readers.loki.record(tenant, record_id)

    @api.get("/v1/metrics", response_model=reading(list[Point]))
    async def metrics(
        query: Annotated[MetricQuery, Query()], tenant: Tenant = telemetry
    ) -> Ok[list[Point]] | Unavailable | Unconfigured:
        """The tenant's latency or errors over time, from Prometheus, through prom-label-proxy."""
        if readers.prometheus is None:
            return Unconfigured()
        return await readers.prometheus.series(tenant, query)

    @api.get("/v1/scores", response_model=reading(Scores))
    async def scores(
        window: Annotated[Window, Query()], tenant: Tenant = telemetry
    ) -> Ok[Scores] | Unavailable | Unconfigured:
        """The tenant's feedback and evaluation scores, from Langfuse, and whether that's all."""
        return await readers.langfuse.scores(tenant, window) if readers.langfuse else Unconfigured()

    @api.get("/v1/feedback", response_model=reading(Feedback))
    async def feedback(
        query: Annotated[FeedbackQuery, Query()], tenant: Tenant = telemetry
    ) -> Ok[Feedback] | Unavailable | Unconfigured:
        """The tenant's feedback and evaluations from Langfuse, or one workspace's, by day.

        The window is at most 91 days. Every score in it is read and summed, within the read's
        bounds: ``complete`` is false where one was reached.
        """
        if not readers.langfuse:
            return Unconfigured()
        return await read_feedback(readers.langfuse, tenant, query)

    @api.get("/v1/spend", response_model=reading(Spend | None))
    async def spend(tenant: Tenant = spending) -> Ok[Spend | None] | Unavailable | Unconfigured:
        """The tenant's usage and spend, against its budget, from its LiteLLM team."""
        return await readers.litellm.spend(tenant) if readers.litellm else Unconfigured()

    @api.get("/v1/usage", response_model=reading(Usage))
    async def usage(
        query: Annotated[UsageQuery, Query()], tenant: Tenant = spending
    ) -> Ok[Usage] | Unavailable | Unconfigured:
        """The tenant's spend per day from LiteLLM, and each named workspace's, with its budget.

        The window is at most 91 days, and the read is bounded: ``complete`` is false where it
        stopped at a bound. Only the named workspaces' tags are asked after.
        """
        if not readers.litellm:
            return Unconfigured()
        return await read_usage(readers.litellm, tenant, query)

    @api.get("/v1/deployment/tenants")
    async def deployment_tenants(by: Subject = operating) -> DeploymentTenants:
        """Every tenant, with its spend from one LiteLLM team list, for operators."""
        tenants = await grants.tenants(by=by)
        spent = await readers.litellm.every_tenant() if readers.litellm else Unconfigured()
        return DeploymentTenants(tenants=tenants, spend=spent)

    @api.get("/v1/deployment/links")
    async def links(
        trace_id: Id | None = None,
        session_id: Id | None = None,
        run_id: Id | None = None,
        tenant_id: TenantId | None = None,
        by: Subject = operating,
    ) -> Links:
        """Deep links into Langfuse and Grafana, which aren't tenant-scoped, for operators.

        What those tools show isn't behind portalr's gates, so each call that makes a link is
        recorded: who, the kinds of id, and the tenant's id if one was asked for, never a trace's,
        a session's or a run's, nor a URL. A tenant that doesn't exist is refused, and nothing is
        recorded for a refusal.
        """
        if tenant_id is not None and tenant_id not in await grants.tenants(by=by):
            raise _refusal("invalid", f"no tenant {tenant_id}")
        langfuse, grafana = readers.langfuse, readers.grafana
        made = Links(
            langfuse_trace=langfuse.trace_link(trace_id) if langfuse and trace_id else None,
            langfuse_session=langfuse.session_link(session_id) if langfuse and session_id else None,
            langfuse_tenant=langfuse.tenant_traces_link(tenant_id)
            if langfuse and tenant_id
            else None,
            grafana_trace=grafana.trace_link(trace_id) if grafana and trace_id else None,
            grafana_logs=grafana.run_logs_link(run_id) if grafana and run_id else None,
            grafana_tenant_logs=grafana.tenant_logs_link(tenant_id)
            if grafana and tenant_id
            else None,
            grafana_tenant_traces=grafana.tenant_traces_link(tenant_id)
            if grafana and tenant_id
            else None,
        )
        kinds = [
            kind
            for kind, given in (
                ("trace", trace_id),
                ("session", session_id),
                ("run", run_id),
                ("tenant", tenant_id),
            )
            if given is not None
        ]
        # A record is of links made: of the tools that have one; with none, nothing is recorded.
        linked = {name.partition("_")[0] for name, value in made if value is not None}
        tools = [tool for tool in ("langfuse", "grafana") if tool in linked]
        if kinds and tools:
            record_links(by, kinds=kinds, tenant=tenant_id, tools=tools)
        return made

    if people is not None:
        _naming(api, grants, people, current)
    if relay is not None:
        _analytics(api, grants, relay, current)
    if invite is not None:
        _invitations(api, grants, invite, current, readers.analytics)
        _tenant_creation(api, grants, invite, operating)
    router.include_router(api)

    return router


async def _operates(grants: Grants, who: Caller) -> bool:
    """Whether the caller is an operator: may read the deployment."""
    return await grants.check(DEPLOYMENT_CHECK, who.subject, READ_DEPLOYMENT, DEPLOYMENT)


MAX_PEOPLE: Final = 100
"""How many people one read of their emails may ask after."""


async def _visible(
    grants: Grants, who: Caller, tenant: TenantId | None, ids: list[str]
) -> list[str]:
    """The ids whose emails the caller may see: no Supabase call is made for any other.

    An operator sees anyone's, with or without a tenant. Any other person who is a member of the
    tenant sees its members'. A key sees no one: only a person sees people.
    """
    if not isinstance(who.subject, User):
        raise _refusal("forbidden", "only a person sees other people")
    tenant = tenant or who.tenant
    if tenant is not None and who.tenant is not None and who.tenant != tenant:
        raise _refusal("forbidden", "this caller's key is for another tenant")
    if await _operates(grants, who):
        return ids
    if tenant is None or await grants.member(tenant, who.subject.id) is None:
        raise _refusal("forbidden", "the caller may not see people here")
    members = await asyncio.gather(*(grants.member(tenant, each) for each in ids))
    return [each for each, member in zip(ids, members, strict=True) if member is not None]


def _naming(router: APIRouter, grants: Grants, people: People, current: Any) -> None:
    @router.get("/v1/people", response_model=Names)
    async def names(
        response: Response,
        id: Annotated[list[Id], Query(min_length=1, max_length=MAX_PEOPLE)],
        x_tenant: TenantHeader = None,
        who: Caller = current,
    ) -> Names:
        """The emails of people, by user id: of the tenant ``X-Tenant`` names, for its members.

        An operator sees anyone's email, with or without a tenant; a member of the tenant sees
        its other members'. An id the caller may not see, with no user or with no email, is left
        out, alike, and Supabase is asked only about the ids the caller may see. At most 100 ids.
        The answer is personal data and is not to be kept, so it is ``no-store``.
        """
        response.headers["Cache-Control"] = "no-store"
        visible = await _visible(grants, who, x_tenant, list(dict.fromkeys(id)))
        got: Mapping[str, str] = await people(visible) if visible else {}
        return Names(people={each: email for each in visible if (email := got.get(each))})


def _refused(error: GrantrError) -> HTTPException:
    return _refusal("forbidden" if isinstance(error, Forbidden) else "invalid", str(error))


def _tenant_creation(router: APIRouter, grants: Grants, invite: Invite, operating: Any) -> None:
    failed = {
        "model": Refused,
        "description": "Supabase Auth didn't invite or find the owner: `invite_failed`",
    }

    @router.post(
        "/v1/deployment/tenants",
        status_code=201,
        responses={502: failed},
        response_model=CreatedTenant,
    )
    async def create_tenant(
        body: Annotated[NewTenant, Body()], by: Subject = operating
    ) -> CreatedTenant:
        """Create a tenant, with its first owner invited, or found, by email, for operators.

        Only operators, who may create tenants, get past the checks, which come before Supabase is
        asked about anyone: a tenant that exists is refused without an invitation, so a repeated
        request invites no one again and creates nothing twice. The email is never logged or
        answered with: the answer names the tenant and the owner's user id.
        """
        # grantr checks this again on every call below, but its refusals come after the email is
        # read: asking here answers a caller who may not with a plain 403 first, whatever they sent.
        if not await grants.check(DEPLOYMENT_CHECK, by, "grantr:create_tenant", DEPLOYMENT):
            raise _refusal("forbidden", "the caller may not create tenants")
        email = body.owner_email.strip()
        if len(email) > MOST_EMAIL or not EMAIL.fullmatch(email):
            raise _refusal("invalid", "the owner's email isn't an email address")
        if body.tenant in await grants.tenants(by=by):
            raise _refusal("invalid", f"{body.tenant} exists")
        try:
            owner = await invite(email)
        except InviteFailed as error:
            detail = {"type": "invite_failed", "message": str(error)}
            raise HTTPException(status_code=502, detail=detail) from error
        try:
            await grants.create_tenant(body.tenant, owner=owner, by=by)
        except (Forbidden, Invalid) as error:
            raise _refused(error) from error
        except Exception as error:
            # A storage error: the owner was invited, and no tenant was made. What storage said
            # may name the owner or the tenant, so none of it is answered.
            detail = {"type": "unavailable", "message": "the tenant couldn't be created"}
            raise HTTPException(status_code=503, detail=detail) from error
        return CreatedTenant(tenant=body.tenant, owner=owner)


def _invitations(
    router: APIRouter,
    grants: Grants,
    invite: Invite,
    current: Any,
    analytics: Analytics | None,
) -> None:
    failed = {
        "model": Refused,
        "description": "Supabase Auth didn't invite or find the person: `invite_failed`",
    }

    @router.post("/v1/invites", status_code=201, responses={502: failed})
    async def invite_member(
        body: Annotated[NewInvite, Body()],
        background: BackgroundTasks,
        x_tenant: TenantHeader = None,
        who: Caller = current,
    ) -> Invited:
        """Invite someone to the tenant: Supabase Auth creates or finds them, grantr adds them.

        It needs ``grantr:add_member``, which is checked before Supabase is asked, and again
        when grantr adds the member. Inviting a member again succeeds, and changes nothing.
        """
        tenant = x_tenant or who.tenant
        if tenant is None:
            raise _refusal("tenant_required", "name the tenant with X-Tenant")
        if who.tenant is not None and who.tenant != tenant:
            raise _refusal("forbidden", "this caller's key is for another tenant")
        if not await grants.check(tenant, who.subject, "grantr:add_member", TENANT):
            raise _refusal("forbidden", f"the caller may not add members to {tenant}")
        try:
            user = await invite(body.email)
        except InviteFailed as error:
            detail = {"type": "invite_failed", "message": str(error)}
            raise HTTPException(status_code=502, detail=detail) from error
        if await grants.member(tenant, user) is None:
            try:
                await grants.add_member(tenant, User(id=user), by=who.subject)
            except (Forbidden, Invalid) as error:
                raise _refused(error) from error
        if analytics is not None and (actor := actor_of(who.subject)) is not None:
            # Recorded after the answer is sent: analytics never slows or fails an invitation.
            kind, by = actor
            background.add_task(
                analytics.capture,
                tenant,
                "member.invited.v1",
                by,
                actor=kind,
                props={"outcome": "invited"},
            )
        return Invited(tenant=tenant, user=user)


def _analytics(router: APIRouter, grants: Grants, relay: Relay, current: Any) -> None:
    """The relay's routes, for a signed-in person only: a key or an agent sends no events."""

    async def person(who: Caller = current) -> str:
        if not isinstance(who.subject, User):
            raise _refusal("forbidden", "only a signed-in person sends product analytics")
        return who.subject.id

    signed_in = Depends(person)

    @router.get("/v1/analytics/consent")
    async def read_consent(user: str = signed_in) -> Answer:
        """The person's answer to product analytics: no until they say yes."""
        return Answer(given=await relay.consent.given(user))

    @router.put("/v1/analytics/consent")
    async def answer(body: Annotated[Answer, Body()], user: str = signed_in) -> Answered:
        """Record the person's answer. A no deletes every event of theirs at once."""
        await relay.consent.give(user, yes=body.given)
        if body.given:
            return Answered(given=True)
        return Answered(given=False, deleted=await relay.analytics.forget(user))

    @router.post("/v1/analytics/session")
    async def session(user: str = signed_in) -> Session:
        """A session id signed for the person, which their browser sends with its events."""
        return Session(session=relay.sign(user))

    too_large = {"model": Refused, "description": "The body is over 16 KB: `too_large`"}
    too_fast = {"model": Refused, "description": "Past the person's pace: `too_fast`"}

    @router.post("/v1/events", status_code=202, responses={413: too_large, 429: too_fast})
    async def events(
        request: Request,
        x_tenant: TenantHeader = None,
        user: str = signed_in,
    ) -> Relayed:
        """A batch of the person's events in a tenant they belong to, kept as the registry says.

        Without the person's yes, nothing is kept, and the answer says so.
        """
        raw = await request.body()
        if len(raw) > MOST_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"type": "too_large", "message": f"a batch is {MOST_BYTES} bytes at most"},
            )
        try:
            batch = Batch.model_validate_json(raw)
        except ValidationError as error:
            raise HTTPException(
                status_code=422, detail={"type": "invalid", "message": str(error.error_count())}
            ) from error
        if x_tenant is None:
            raise _refusal("tenant_required", "name the tenant with X-Tenant")
        if await grants.member(x_tenant, user) is None:
            raise _refusal("forbidden", f"the caller isn't a member of {x_tenant}")
        session_id = relay.session_of(user, batch.session)
        if session_id is None:
            raise _refusal("forbidden", "the session isn't one portalr signed for this person")
        if not await relay.consent.given(user):
            return Relayed(recorded=0, dropped=len(batch.events))
        wait = relay.limiter.spend(user, len(batch.events))
        if wait is not None:
            raise HTTPException(
                status_code=429,
                detail={"type": "too_fast", "message": "too many events; send them later"},
                headers={"Retry-After": str(max(1, round(wait)))},
            )
        named = [
            (event.event, kept(event, REGISTRY[event.event]))
            for event in batch.events
            if event.event in REGISTRY
        ]
        written = bool(named) and await relay.analytics.capture_many(
            x_tenant, user, named, session_id=session_id
        )
        recorded = len(named) if written else 0
        return Relayed(recorded=recorded, dropped=len(batch.events) - recorded)
