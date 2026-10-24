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
from typing import Annotated, Any, Final, cast

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
from portalr.analytics.consent import Consent
from portalr.analytics.relay import (
    MOST_BYTES,
    Answer,
    Answered,
    Batch,
    Consented,
    Relay,
    Relayed,
    Session,
)
from portalr.analytics.replay import MOST_REPLAY_BYTES, ReplayBatch, expansion
from portalr.fastapi.site import Site, Surfaces
from portalr.fastapi.ui import ui_router
from portalr.invites import Invite, InviteFailed
from portalr.people import People
from portalr.readers import (
    Adoption,
    AdoptionQuery,
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
from portalr.readers.analytics import Analytics, actor_of
from portalr.readers.loki import RECORD_ID
from portalr.readers.query import Id
from portalr.readers.tempo import carries_analytics_session, for_tenant
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
    replay: bool = False
    """Whether the deployment records session replays, with a person's own yes to them (portalr
    ADR-0077): off unless an operator turns it on, after the privacy review."""


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
    umami_journeys: str | None = None
    """portalr's website in Umami, every tenant's journeys: made with a tenant's id, as the
    other links for a tenant are, though Umami isn't split by tenant."""


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
            replay=relay is not None
            and relay.replay is not None
            and relay.umami is not None
            and await relay.umami.replay_enabled(),
        )

    @api.get("/v1/traces", response_model=reading(list[TraceSummary]))
    async def traces(
        query: Annotated[TraceQuery, Query()], tenant: Tenant = telemetry, who: Caller = current
    ) -> Ok[list[TraceSummary]] | Unavailable | Unconfigured:
        """The tenant's traces, a thread's or a run's, from Tempo.

        An analytics session's are for operators alone (portalr ADR-0073).
        """
        if query.analytics_session is not None and not await _operates(grants, who):
            raise _refusal("forbidden", "only operators find traces by analytics session")
        return await readers.tempo.search(tenant, query) if readers.tempo else Unconfigured()

    @api.get("/v1/traces/{trace_id}", response_model=reading(Trace | None))
    async def trace(
        trace_id: Id,
        response: Response,
        content: bool = False,
        span: Id | None = None,
        tenant: Tenant = telemetry,
        who: Caller = current,
    ) -> Ok[Trace | None] | Unavailable | Unconfigured:
        """A trace, if it is the tenant's: its spans, for its waterfall.

        Only the attributes known to be safe are shown, and a span's analytics session only to
        operators. ``content=true`` and ``span`` ask for one
        span's others, its prompt and completion among them, and nothing of any other span's; the
        answer is not to be kept.
        """
        if content and span is None:
            raise HTTPException(422, "content is asked for a span: name it with span")
        if not readers.tempo:
            return Unconfigured()
        if content:
            response.headers["Cache-Control"] = "no-store"
        read = await readers.tempo.trace(tenant, trace_id, reveal=span if content else None)
        # A request's analytics session is the operators' alone (portalr ADR-0073).
        if (
            isinstance(read, Ok)
            and read.data is not None
            and carries_analytics_session(read.data)
            and not await _operates(grants, who)
        ):
            return Ok(data=for_tenant(read.data))
        return read

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

    @api.get("/v1/adoption", response_model=reading(Adoption))
    async def adoption(
        query: Annotated[AdoptionQuery, Query()], tenant: Tenant = telemetry
    ) -> Ok[Adoption] | Unavailable | Unconfigured:
        """The tenant's adoption from its product analytics (portalr ADR-0071).

        People active each day, who used each integration, the funnel from a page to a thread to
        a message, and weekly retention, over a window of at most 91 days. People are counted by
        a keyed hash of their id, and only those who said yes. ``complete`` is false where the
        read stopped at its deadline.
        """
        if not readers.analytics:
            return Unconfigured()
        return await readers.analytics.adoption(tenant, query)

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
        """Deep links into Langfuse, Grafana and Umami, which aren't tenant-scoped, for operators.

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
            umami_journeys=readers.umami.website_link() if readers.umami and tenant_id else None,
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
        tools = [tool for tool in ("langfuse", "grafana", "umami") if tool in linked]
        if kinds and tools:
            record_links(by, kinds=kinds, tenant=tenant_id, tools=tools)
        return made

    if people is not None:
        _naming(api, grants, people, current)
    if relay is not None:
        _analytics(api, grants, relay, current, ui)
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


def _analytics(router: APIRouter, grants: Grants, relay: Relay, current: Any, ui: Path) -> None:
    """The relay's routes, for a signed-in person only: a key or an agent sends no events.

    Each request is counted against the person's pace before anything else is read, and past it
    refused; but never their answer, so a person can always take their yes back.
    """

    def signed_in_person(who: Caller) -> str:
        if not isinstance(who.subject, User):
            raise _refusal("forbidden", "only a signed-in person sends product analytics")
        return who.subject.id

    async def person(who: Caller = current) -> str:
        user = signed_in_person(who)
        wait = relay.requests.spend(user, 1)
        if wait is not None:
            raise _too_fast(wait)
        return user

    async def answering(who: Caller = current) -> str:
        user = signed_in_person(who)
        # Counted, so answers drain the person's pace for the other routes; never refused.
        relay.requests.spend(user, 1)
        return user

    signed_in = Depends(person)
    answering_person = Depends(answering)

    @router.get("/v1/analytics/consent", responses={429: TOO_FAST})
    async def read_consent(user: str = signed_in) -> Consented:
        """The person's answer to product analytics: no until they say yes.

        ``deleting`` says a deletion their no asked for isn't done yet: tried again now, and by
        the background pass, until it is.
        """
        await relay.settle_if_owed(user)
        return Consented(
            given=await relay.consent.given(user),
            deleting=await relay.consent.owes(user) is not None,
        )

    @router.put("/v1/analytics/consent")
    async def answer(body: Annotated[Answer, Body()], user: str = Depends(answering)) -> Answered:
        """Record the person's answer. Taking a yes back deletes their events at once.

        A deletion ClickHouse can't take stays owed, and is tried again on the person's next
        request, and by a background pass every few minutes: ``deleted`` says whether it is
        done. A yes later doesn't cancel it. It is never refused for the person's pace: a
        withdrawal always lands.
        """
        return await relay.answer(user, yes=body.given)

    @router.post("/v1/analytics/session", responses={429: TOO_FAST})
    async def session(user: str = signed_in) -> Session:
        """A session id signed for the person, which their browser sends with its events."""
        return Session(session=relay.sign(user))

    @router.post(
        "/v1/events",
        status_code=202,
        responses={413: TOO_LARGE, 422: INVALID, 429: TOO_FAST},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _inlined(Batch.model_json_schema())}},
            }
        },
    )
    async def events(
        request: Request,
        x_tenant: TenantHeader = None,
        user: str = signed_in,
    ) -> Relayed:
        """A batch of the person's events in a tenant they belong to, kept as the registry says.

        Without the person's yes, nothing is kept, and the answer says so.
        """
        batch = await _batch(request)
        if x_tenant is None:
            raise _refusal("tenant_required", "name the tenant with X-Tenant")
        if await grants.member(x_tenant, user) is None:
            raise _refusal("forbidden", f"the caller isn't a member of {x_tenant}")
        session_id = relay.session_of(user, batch.session)
        if session_id is None:
            raise _refusal("forbidden", "the session isn't one portalr signed for this person")
        wait = relay.limiter.spend(user, len(batch.events))
        if wait is not None:
            raise _too_fast(wait)
        return await relay.record(x_tenant, user, batch, session_id)

    if relay.replay is not None and relay.umami is not None:
        _replay(router, grants, relay, relay.replay, signed_in, answering_person, ui)


def _replay(
    router: APIRouter,
    grants: Grants,
    relay: Relay,
    replay: Consent,
    signed_in: Any,
    answering: Any,
    ui: Path,
) -> None:
    """Session replay's routes, where the deployment records replays (portalr ADR-0077)."""
    # The app's own stylesheets, by file name: the text a replay is given for a stylesheet it names.
    sheets = {
        sheet.name: sheet.read_text(encoding="utf-8") for sheet in (ui / "app").glob("assets/*.css")
    }

    @router.get("/v1/analytics/replay/consent", responses={429: TOO_FAST})
    async def read_replay_consent(user: str = signed_in) -> Consented:
        """The person's answer to session replay: no until they say yes, apart from analytics'."""
        return Consented(
            given=await replay.given(user), deleting=await replay.owes(user) is not None
        )

    @router.put("/v1/analytics/replay/consent")
    async def answer_replay(body: Annotated[Answer, Body()], user: str = answering) -> Answered:
        """Record the person's answer to replay. Taking a yes back deletes their replays at once.

        A yes needs the person's yes to analytics first; a no is never refused.
        """
        try:
            return await relay.answer_replay(user, yes=body.given)
        except ValueError as error:
            raise _refusal("invalid", str(error)) from error

    @router.post(
        "/v1/analytics/replay",
        status_code=202,
        responses={413: REPLAY_TOO_LARGE, 422: INVALID, 429: REPLAY_TOO_FAST},
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": _inlined(ReplayBatch.model_json_schema())}
                },
            }
        },
    )
    async def replays(
        request: Request,
        x_tenant: TenantHeader = None,
        user: str = signed_in,
    ) -> Relayed:
        """A batch of the person's replay events in a tenant they belong to, forwarded to Umami.

        Only with their yes to replay and to analytics; and only if every value in it is masked:
        a batch with any word, input or address in it is dropped whole.
        """
        batch = await _batch(request, ReplayBatch, MOST_REPLAY_BYTES)
        if x_tenant is None:
            raise _refusal("tenant_required", "name the tenant with X-Tenant")
        if await grants.member(x_tenant, user) is None:
            raise _refusal("forbidden", f"the caller isn't a member of {x_tenant}")
        if relay.session_of(user, batch.session) is None:
            raise _refusal("forbidden", "the session isn't one portalr signed for this person")
        # A batch costs its size and what the stylesheets it names would add to it.
        _, added = expansion(batch.events, sheets)
        size = len(batch.model_dump_json().encode()) + added
        wait = relay.replay_limiter.spend(user, max(size, 8 * 1024))
        if wait is not None:
            raise _too_fast(wait)
        return await relay.record_replay(x_tenant, user, batch, sheets)


TOO_LARGE: Final = {"model": Refused, "description": "The body is over 16 KB: `too_large`"}
TOO_FAST: Final = {"model": Refused, "description": "Past the person's pace: `too_fast`"}
REPLAY_TOO_LARGE: Final = {
    "model": Refused,
    "description": "The body is over 512 KiB: `too_large`",
}
REPLAY_TOO_FAST: Final = {
    "model": Refused,
    "description": "Past the person's pace in bytes of replay: `too_fast`",
}
INVALID: Final = {"model": Refused, "description": "Not a batch the relay takes: `invalid`"}


def _inlined(schema: dict[str, Any]) -> dict[str, Any]:
    """A model's JSON Schema with its own definitions written in place, as OpenAPI takes it.

    The events route reads its body by hand, to stop at the 16 KB cap as it comes, so FastAPI
    doesn't know its model: the schema is given in ``openapi_extra``, where a ``$defs`` reference
    would point nowhere, so the definitions are inlined.
    """
    definitions: dict[str, Any] = schema.pop("$defs", {})

    def inline(node: object) -> object:
        if isinstance(node, dict):
            mapping = cast(dict[str, object], node)
            reference = mapping.get("$ref", "")
            if isinstance(reference, str) and reference.startswith("#/$defs/"):
                return inline(definitions[reference.removeprefix("#/$defs/")])
            return {key: inline(value) for key, value in mapping.items()}
        if isinstance(node, list):
            return [inline(item) for item in cast(list[object], node)]
        return node

    return cast(dict[str, Any], inline(schema))


def _too_fast(wait: float) -> HTTPException:
    seconds = str(max(1, round(wait)))
    return HTTPException(
        status_code=429,
        detail={"type": "too_fast", "message": "too many requests; try again later"},
        headers={"Retry-After": seconds},
    )


async def _batch[B: BaseModel](
    request: Request, model: type[B] = Batch, most: int = MOST_BYTES
) -> B:
    """The request's batch, read no further than its cap: a longer body is refused as it comes."""
    too_large = HTTPException(
        status_code=413,
        detail={"type": "too_large", "message": f"a batch is {most} bytes at most"},
    )
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > most:
        raise too_large
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > most:
            raise too_large
    try:
        return model.model_validate_json(bytes(raw))
    except ValidationError as error:
        raise HTTPException(
            status_code=422,
            detail={"type": "invalid", "message": f"{error.error_count()} faults in the batch"},
        ) from error
