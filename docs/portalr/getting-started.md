# Getting started

This page gets portalr's two UIs, `app` and `admin`, running inside an application you already have: install the wheel, mount the router, give the UIs your Supabase project, and sign in. portalr is a Python router your application mounts beside the libraries'; the UIs are static files it carries and serves ([ADR-0001](adr/0001-a-router-the-application-mounts.md)).

!!! note "What is built"

    Every area of both UIs described in these guides is built and tested. [stackr's template](../stackr/guides/template.md) asks a `portal` question and mounts portalr for you ([stackr ADR-0038](../stackr/adr/0038-portalr-in-the-template.md)); this page is for an application that mounts it itself, and says what the template does for you. The template passes `people=` and `invite=` when it has the gateway's address and its secret key, and stackr's smoke test runs a few scenarios against a generated application ([ADR-0040](adr/0040-scenarios-against-a-generated-application-and-size-budgets.md)). Not built yet: magic links and other sign-in providers (a password signs in).

## What you need

portalr reads and writes through the packages you already run, so it needs their surfaces:

| Needs | For |
|---|---|
| [grantr](../grantr/index.md) | Who may see and do what. Every read and command is checked by it, and the UIs ask it what to show |
| [artifactr](../artifactr/index.md)'s router | The app's workspaces, threads, artifacts and proposals |
| [reflexr](../reflexr/index.md)'s router | The app's rules and runs, and admin's Runs |
| [Supabase Auth](../stackr/guides/supabase.md) | Signing in, inviting people, and naming them by email |
| Any of Tempo, Loki, Prometheus, Langfuse, LiteLLM and Grafana | Admin's traces, logs and health, feedback, spend, and the operators' links. Each is optional: a tool you don't run is "not configured", and only its own area says so |

[stackr](../stackr/index.md)'s stack runs all of them, and its template generates an application that mounts the libraries, and portalr beside them when its `portal` question is answered yes, which is the default with grantr.

## Install

portalr needs Python 3.12 or newer. Its wheel carries the two built UIs, which Vite builds into it, so install the wheel, not the source. It is on PyPI, as are the two packages it requires, `grantr[fastapi]` and `lattice-core-ai`.

=== "From PyPI"

    ```bash
    uv add portalr
    ```

    Each package's GitHub [release](https://github.com/alexnodeland/lattice/releases) has the same wheel and sdist attached, with their provenance attested ([ADR-0023](../adr/0023-publishing-to-pypi-from-the-release-workflow.md)).

=== "From a checkout"

    For a change on `main` before its release, build the wheel from a checkout of lattice, with [Bun](https://bun.sh) and [moon](https://moonrepo.dev) installed (`proto use` installs them):

    ```bash
    git clone https://github.com/alexnodeland/lattice
    cd lattice
    bun install --frozen-lockfile
    moon run portalr:build        # both UIs, then the wheel: packages/portalr/dist/portalr-<version>-py3-none-any.whl
    ```

    Then, in your application's project, with `LATTICE` set to the checkout's path:

    ```bash
    uv add "lattice-core-ai @ $LATTICE/packages/lattice-core" \
           "grantr[fastapi] @ $LATTICE/packages/grantr" \
           $LATTICE/packages/portalr/dist/portalr-*.whl
    ```

    `lattice-core-ai` comes from the checkout too, so that it is the one the checkout's grantr and portalr were written against; PyPI's can be older.

    The built wheel holds `portalr/static/app/` and `portalr/static/admin/`; `moon run portalr:build` and that install were run to write this page.

!!! warning "A git install has no UIs"

    `pip install "portalr @ git+https://github.com/alexnodeland/lattice#subdirectory=packages/portalr"` installs the Python, but the UIs are not in git: they are built into the wheel. The router would have nothing to serve at `/portalr/app/` and `/portalr/admin/`.

## Mount the router

`portalr_router` takes what it needs from your application and returns a FastAPI router to mount at `/portalr`:

| Argument | Is |
|---|---|
| `resolve_actor` | Authenticates a request, as grantr's router does: it returns a `Caller`, or raises `Unauthorized` |
| `grants` | grantr's `Grants`, with portalr's catalog, `portalr.actions.ACTIONS`, among its catalogs |
| `readers` | The tools your stack runs, each optional |
| `invite` | Supabase Auth's admin API, as a function from an email to a user id. Without it, there is no invitation route and no way to create a tenant from admin |
| `site` | Your Supabase project's URL and *publishable* key, and where you mounted each router |
| `people` | Optional. Names people by email: a function from user ids to the emails it can find, such as `portalr.people.SupabasePeople(url=, secret_key=)` over Supabase Auth's admin API. Without it, there is no people route, and the UIs show people by a short id |
| `relay` | Optional. Product analytics from people's browsers, with their consent ([lattice RFC-0008](../rfcs/0008-portalr-product-analytics.md)): `portalr.analytics.Relay(analytics, consent, limiter, grants=grants)`, over ClickHouse, people's answers (`portalr.analytics.sql.SqlConsent`, with the `sql` extra) and their pace. Without it, there are no analytics routes |
| `models` | Optional. The models a workspace allows a turn to name ([ADR-0086](adr/0086-the-composer-chooses-the-model-of-the-next-turn.md)): `async (tenant, workspace) -> list[portalr.models.OfferedModel]`, read from the same source as the runner's `artifactr:use_model` check. Without it, there is no models route, and the composer offers no choice |

```python
from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr import Grants, InMemoryStorage, User
from grantr.fastapi import Caller, Unauthorized
from portalr.actions import ACTIONS
from portalr.fastapi import Site, portalr_router
from portalr.readers import Readers

grants = Grants(InMemoryStorage(), catalogs=[ACTIONS])


async def resolve_actor(connection: HTTPConnection) -> Caller:
    """Who the request is from. A stand-in: see below for a real one."""
    if user := connection.headers.get("x-user"):
        return Caller(User(id=user))
    raise Unauthorized("sign in")


async def invite(email: str) -> str:
    """A stand-in for Supabase Auth's admin API: the user's id is the email's local part."""
    return email.partition("@")[0]


async def people(ids):
    """A stand-in for ``SupabasePeople``: everyone's email is their id at example.com."""
    return {each: f"{each}@example.com" for each in ids}


app = FastAPI()
app.include_router(
    portalr_router(
        resolve_actor=resolve_actor,
        grants=grants,
        readers=Readers(),
        invite=invite,
        site=Site(supabase_url="https://project.supabase.co", supabase_key="sb_publishable_x"),
        people=people,
    ),
    prefix="/portalr",
)
```

`resolve_actor` here trusts an `x-user` header, which is fine for a test and for nothing else. A real one verifies the access token Supabase Auth issued, from the `Authorization: Bearer` header, or from the `access_token` query on a WebSocket, which a browser opens without headers. Supabase now signs tokens with an asymmetric key (ES256 by default) that it publishes at a JWKS URL, so you verify against that, as [stackr's template](../stackr/guides/template.md) does in its `auth.py` (its `AUTH_JWKS_URL` setting):

```python
import asyncio
import os

import jwt


def token_resolver(keys: jwt.PyJWKClient, audience: str = "authenticated"):
    """A ``resolve_actor`` that verifies Supabase's access tokens against its published keys."""

    async def resolve_actor(connection: HTTPConnection) -> Caller:
        scheme, _, token = connection.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" and connection.scope["type"] == "websocket":
            token, scheme = connection.query_params.get("access_token", ""), "bearer"
        if scheme.lower() != "bearer" or not token:
            raise Unauthorized("sign in")
        try:
            # Fetching a key may call out to Supabase, so it runs in a thread.
            key = await asyncio.to_thread(keys.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["ES256"],
                audience=audience,
                options={"require": ["exp", "sub", "aud"]},
            )
        except jwt.PyJWTError as error:
            raise Unauthorized("the access token is not valid") from error
        return Caller(User(id=claims["sub"]))

    return resolve_actor


# In your application: the key set, fetched once and cached.
keys = jwt.PyJWKClient(
    os.environ.get("AUTH_JWKS_URL", "https://project.supabase.co/auth/v1/.well-known/jwks.json"),
    cache_keys=True,
    lifespan=300,
)
resolve_actor = token_resolver(keys)
```

A test of this guide signs a token with a generated key and checks that this function accepts it, and refuses an expired one, one for another audience, and one signed by another key.

!!! note "A project on the legacy JWT secret"

    A Supabase project that still signs with the legacy shared secret issues HS256 tokens: verify those with `algorithms=["HS256"]` and the secret (`SUPABASE_JWT_SECRET`, in the project's settings) in place of `key`. The template accepts either or both. Prefer moving the project to asymmetric keys.

A person's grantr id is their Supabase user's `sub`, an opaque UUID, and grantr holds no names. With `people`, the UIs show people by email, which they ask of `GET /portalr/v1/people` for the people the caller may see ([ADR-0038](adr/0038-people-by-email.md); [what portalr keeps from view](guides/privacy.md#emails-and-names) says who sees whose). Without it, or for an id it can't name, they show the first eight characters of a long id, such as `3f2a91c4…`.

`Site` refuses a secret key: `config.json` is public, and a secret (`sb_secret_…` or a `service_role` JWT) bypasses row security. The `invite` and `people` functions are the only places the secret key lives, in your application.

## What the router serves

| Route | Answers |
|---|---|
| `/portalr/app/` and `/portalr/admin/` | The built UIs: hashed assets cached for good, the index for every client-side route, with a strict Content-Security-Policy |
| `GET /portalr/config.json` | What the UIs need to know about your deployment, below |
| `/portalr/v1/…` | portalr's own reads, its two commands, and, with `people`, the emails of people: [the admin guide](guides/admin.md) and [the operators' runbook](guides/operators.md) say what each is for |

The UIs call the other routers directly, on the same origin and with the same token: a chat goes to artifactr's WebSocket, a rule to reflexr's REST, a grant to grantr's API. Nothing proxies them.

### `config.json`

The UIs read this first. It is public, so it holds no secret:

| Key | Is |
|---|---|
| `supabase.url` | Your Supabase project's URL, or a path on your own origin that leads to it |
| `supabase.key` | Its publishable key |
| `surfaces` | Where you mounted each router: `artifactr` (default `/artifactr/v1`), `reflexr` (default `/reflexr/v1`), `grantr` (default `""`: its paths carry `/grantr/v1` themselves), `portalr` (default `/portalr/v1`) and `relayr` (default `null`: the application has no tracker; give the origin of relayr's tracker reads, `""` on this one, and runs link to what they filed). Pass `Surfaces(...)` in `Site` if you mounted them elsewhere |
| `readers` | Which tools are configured, by name: `tempo`, `loki`, `prometheus`, `langfuse`, `litellm`, `grafana`, `analytics` and `umami`, each true or false |
| `people` | Whether the router names people by email: true where `people` was passed |
| `editors` | Each native file's app's hosted editor, by its integration, such as `files:wordcraft`: pass `editors={...}` in `Site` where you serve one on an origin of its own ([ADR-0049](adr/0049-checking-a-native-file-out-and-in.md)). Empty by default |
| `apps` | The origin mini apps run on: pass `apps=` in `Site` where you serve their sandbox, below. `null` by default, and apps are then shown as their label and summary |
| `links` | Each connected app an integration brings, by its key, at its address, such as `{"tracker:plane": "http://127.0.0.1:8090/"}`: pass `links=` in `Site`. The admin opens it beside the integration's switch, and the palette lists it where the integration is on ([ADR-0088](adr/0088-connected-apps-opened-from-the-admin-and-the-palette.md)). Empty by default |
| `origin` | The portal's own origin, where you pass `origin=` in `Site`; `null` by default, and the UIs then trust the address they are at ([ADR-0084](adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md)) |
| `aliases` | Each other origin the portal is reached at, such as a tailnet name beside its loopback address, to the apps' origin and the editors beside it, `{"apps": ..., "editors": {...}, "links": {...}}`: pass `aliases={extra: beside(portal, extra, apps=..., editors=..., links=...)}` in `Site`, and give `SandboxOrigin` and each `editor_app` every origin. The UIs use the place of the address they are at, and at one named nowhere say where to open the portal. Empty by default |
| `brand` | The deployment's brand kit: its hash, identity, words, and where its stylesheet and marks are served. Pass `brand=Path(...)` in `Site` to point at a kit's folder ([lattice RFC-0007](../rfcs/0007-portalr-brand-kits.md)); it is read and checked as the site is made. `null` by default, for portalr's own look. The UIs draw the kit's mark and the product's name in the header, and its words when signing in; what a kit does not reach yet is listed in the RFC's "Not yet". `portalr brand init` starts a kit and `portalr brand validate` checks one: see [white-labelling the portal](guides/white-labelling.md) |

```python
from httpx import ASGITransport, AsyncClient

async with AsyncClient(transport=ASGITransport(app=app), base_url="http://app") as client:
    config = (await client.get("/portalr/config.json")).json()
    assert sorted(config) == ["aliases", "apps", "brand", "editors", "links", "origin", "people", "readers", "replay", "supabase", "surfaces"]
    assert config["readers"]["tempo"] is False
    assert config["people"] is True
```

### Run mini apps

An agent's mini app runs in a sandbox on an origin of its own, the same site as the portal's, for which nothing sets a cookie ([lattice RFC-0005](../rfcs/0005-forms-dashboards-and-mini-apps.md), [ADR-0051](adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)). Point a host name, such as `apps.example.com`, at the application, add `SandboxOrigin`, which answers that host with the sandbox and nothing else, and name it in `Site`, so the UIs frame it and nothing more. Locally, a second port on 127.0.0.1 is an origin of its own:

```python title="Illustrative"
from portalr.fastapi import SandboxOrigin, Site

site = Site(supabase_url="/", supabase_key="sb_publishable_...", apps="https://apps.example.com")
app.add_middleware(SandboxOrigin, apps="https://apps.example.com", portal="https://app.example.com")
```

Name the same origin to both: `Site` alone frames an origin that nothing answers, and apps show an empty frame. Since the apps' host shares the portal's registrable domain, nothing in the deployment may set a cookie with `Domain=` on it, which the apps' origin would be sent: the portal's own and the edge's cookies are host-only, and its session is in `localStorage`, which the apps' origin can't read.

An app reads nothing of the person's and loads nothing, but it can send what it was given, over WebRTC from a frame it makes, which Chromium lets no page refuse ([ADR-0051](adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)). Apps then run where a workspace switches `ui:mini-apps` on, which is off by default. If an app hasn't run ten seconds after its frame loads, its card says so and offers Try again, rather than showing a blank frame.

## Name portalr's actions to grantr

portalr's catalog has three actions, which grantr's roles give out:

| Action | Held by | For |
|---|---|---|
| `portalr:read_telemetry` | A tenant's `owner` and `admin` | Feedback, traces, logs, health |
| `portalr:read_spend` | A tenant's `owner` and `admin` | Spend and usage |
| `portalr:read_deployment` | `operator` | The tenant list, creating a tenant, and the tools' links |

Pass `catalogs=[ACTIONS, ...]` to `Grants`, as above, along with artifactr's and reflexr's. A viewer or an editor of a workspace is not shown admin: it opens for a tenant's owners and admins, and for operators.

```python
from grantr.core import TENANT

await grants.first_operator("root")
await grants.create_tenant("acme", owner="alice", by=User(id="root"))

assert await grants.check("acme", User(id="alice"), "portalr:read_telemetry", TENANT)
assert not await grants.check("acme", User(id="alice"), "portalr:read_deployment", TENANT)
```

## Sign in

Open `/portalr/app/` for the people's UI, or `/portalr/admin/` for the admin UI. Both sign in through Supabase Auth with an email and a password, keep the session in the browser's `localStorage`, refresh the token, and send it with every request. Signing out ends the session in that browser alone. A request the server refuses as unsigned ends the session too, and the UI goes back to the sign-in page.

- **The app** lists the tenants someone belongs to: none is "no access", one goes straight to it. Then it lists the workspaces they can open.
- **Admin** opens on the tenant someone last used, or their only one; operators open on "All tenants"; someone with no tenant to administer is told there is no access.

Next: [the app](guides/app.md), [the admin UI](guides/admin.md), and, for operators, [the runbook](guides/operators.md). Read [what portalr keeps from view](guides/privacy.md) before you give anyone admin.
