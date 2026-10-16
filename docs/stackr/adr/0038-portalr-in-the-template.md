# ADR-0038: portalr in the template

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Builds the template's half of [portalr's phase 7](../../portalr/rfcs/0001-v0.1-implementation-plan.md) and [lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md)'s "The template": an application generated with grantr can mount portalr's router and serve its two UIs.

## Context

RFC-0002 has the template gain a `portal` question, on when `access` is `grantr`, which portalr needs to say who may read what. The application mounts `portalr_router` beside the libraries', with the readers for the tools the stack runs, and installs portalr from its released wheel. Three things were open.

- **portalr's UIs are in its wheel, not in its source.** Vite builds them into `src/portalr/static/`, which git ignores. The template installs every library from lattice at the commit it was rendered from, because none is on PyPI, so an application that does the same for portalr has a router and no UIs.
- **The Supabase project is the application's to name.** The UIs sign in to it from the browser, with its publishable key, which `config.json` publishes. The key is a setting that no default can supply.
- **The audit trail has to reach Loki.** portalr's access records and grantr's audit records are logged at INFO, under `portalr.access` and `grantr.audit`; the application's logging leaves loggers without a level at the root's WARNING.

## Decision

- **A `portal` question,** asked only with `access=grantr`, **on by default** (the user's decision, over a recommendation to start off). Its help text says it needs a Supabase project and adds a Bun build to the image, and the guide says that `copier update` of an existing application now asks it. `use_portal` is the derived answer the files read, so that an application without grantr is never given one. Without it, the application is as it was.
- **`portal.py` is a part, like the libraries',** with `migrate`, `lifespan` and `mount`, built over the application's `Access`: the router's `resolve_actor` is the one grantr's admin API uses, and its `Grants` is the application's own, with portalr's catalog (`portalr:read_telemetry`, `read_spend`, `read_deployment`) among the roles' actions. `access.md` gains those three rows, which `scripts/access-matrix` writes and a test compares.
- **It is mounted only where the Supabase project is named** (`PORTAL_SUPABASE_URL`, `PORTAL_SUPABASE_KEY`): without them the router is not mounted, an INFO line says so, and `/` leaves it out. The default application and its tests run as before. portalr's `Site` refuses a secret key, so the browser can't be given one.
- **Each tool is read where its setting names it, and left out where it doesn't.** Tempo, Loki and Prometheus (through prom-label-proxy) by `PORTAL_*_URL`; Langfuse by `LANGFUSE_BASE_URL`, the project's id and its keys; LiteLLM by the gateway's address and `PORTAL_LITELLM_KEY`, **a key of its own that reads spend and nothing else, never the master key** (the user's decision): stackr's `make portal-key` makes it, a view-only admin's key limited to `/team/info`, `/team/list` and `/team/daily/activity`, which on the pinned LiteLLM (v1.103.0) opens those three routes and is refused every other (checked against the proxy, and in the smoke test); Grafana for operators' links. `stackr.env` gives the app profile the stack's addresses for them. Invitations go through Supabase Auth's admin API when `PORTAL_AUTH_URL` and `AUTH_SERVICE_ROLE_KEY` are set, and fail with that reason when they aren't.
- **The image builds the UIs.** A stage of `oven/bun`, pinned by tag and digest at the version lattice's `.prototools` has (`check-template` holds the two together), fetches lattice at the commit `uv.lock` pins portalr at, installs the two UIs' workspaces with the lockfile (with a cache) and builds `app` and `admin` into `/ui`, and `PORTAL_UI_DIR=/ui` points the router at them. The commit is not written a second time: `scripts/build-portal-ui.sh` reads it from `uv.lock`, so the UIs are always the installed router's own. The script is that stage's, and `make portal-ui` runs it on a machine with git and Bun, into `.portal-ui`. This is a stopgap with a date: when portalr is on PyPI, the application installs its wheel, and the stage and the script go.
- **`LOG_CONFIG` puts `portalr.access` and `grantr.audit` at INFO,** without handlers of their own, so their records propagate to the root's, which exports them to Loki.
- **It is checked as everything in the template is.** `check-template` renders fifteen variants, one of them with grantr and without the portal. CI's Template job runs the generated application's own `make check` for the same, so the portal's tests (its config and both UIs served, a read asked of grantr and refused across tenants, the tools and invitations each configured and not, the settings, and `LOG_CONFIG`) run at 100% coverage. The smoke test signs a user in to an application whose image has built the UIs, and checks that it serves both, that the owner reads the tenant's spend, and that a tenant the user isn't in is refused.

- **A single host does not ship an inert portal.** The generated overlay sets `PORTAL_REQUIRED`, so the application stops at startup, saying why, unless the Supabase project is named; it trusts the edge's `X-Forwarded-*` headers (`FORWARDED_ALLOW_IPS`, since only the edge reaches it); and the edge answers GoTrue at `/auth/v1` as well as at its root, because supabase-js reaches Supabase Auth at `<url>/auth/v1` (the admin API stays refused under it). Invitations are off there and say why: GoTrue alone has no gateway behind its private address.

## Options considered

| Option | For | Against |
|---|---|---|
| **Build the UIs in the image (chosen)** | Works from a repository install, as every other library does | Needs git, Bun and the network at build time |
| Install portalr from a release wheel | What RFC-0002 says; no build in the image | No wheel exists until the first release, and a template at a commit would name a release |
| Commit the built UIs | No build | Generated files in the repository, which portalr ADR-0033's notices rely on being built |
| Fail without a Supabase project | Nothing silently off | The default application and every test would need one |

## Consequences

- Easier: `copier copy` gives an application the app and admin UIs, the reads and the audit trail, on the same grantr.
- Harder: the image's build is longer, and fetches lattice from GitHub, as `uv sync` already does.
- Not done: the UIs' scenarios still run against portalr's own test application (`tests/app`), not an application the template generated; the Acceptance job's portalr steps and the size budgets of the plan's phase 7 follow. A single host's overlay does not yet name the tools' addresses.
- When portalr is released, the stage and `scripts/build-portal-ui.sh` go.
