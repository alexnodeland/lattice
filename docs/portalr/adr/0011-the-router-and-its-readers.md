# ADR-0011: The router and its readers

**Status:** Accepted, amended by [ADR-0012](0012-acceptance-against-a-two-tenant-stack.md) and [ADR-0041](0041-first-party-webassembly-in-the-apps-policy.md) (both UIs' policy allows first-party WebAssembly)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md#the-router) designs `portalr_router`, which an application mounts beside the libraries' routers. It serves the two UIs and adds the routes no library has: reading the stack's tools for one tenant, inviting users, and, for operators, the deployment's tenants and deep links. [ADR-0006](0006-shared-stores-every-read-filtered.md) puts every read through one module, `portalr.readers`, which filters it by tenant. Phase 4 builds both, and the RFC leaves some of their details open.

## Decision

- **The router takes two arguments beyond the RFC's four:**
  - `site`: the application's Supabase URL and publishable key, and where it mounts each surface. `config.json` serves them, and the Content-Security-Policy names Supabase.
  - `ui`: where the built UIs are. It is the wheel's own `static/` unless a test passes another.
  - An application mounts the router at `/portalr`. The UIs are at `/portalr/app/` and `/portalr/admin/`, and the routes at `/portalr/v1`.
- **The UIs:**
  - A file under `assets/`, which Vite names by its hash, is cached for a year as `immutable`. Anything else is `no-cache`.
  - A path that names no file gets the UI's `index.html`, for its client-side routes. A path that resolves outside the UI gets the index, never the file.
  - Every response carries a strict Content-Security-Policy: the UI's own origin, plus Supabase for `connect-src`. It also sets `nosniff` and `no-referrer`.
- **A read never fails for its tool,** so an admin card fails alone, and Schemathesis's check against server errors holds. Each read answers 200, with one of:
  - `{"status": "ok", "data": ...}`;
  - `{"status": "unavailable", "reason": ...}` when the tool is down or answers an error;
  - `{"status": "unconfigured"}` when the application runs without it.
- **A `Tenant` is made only by `allowed()`,** which only the router calls, after grantr's check of `portalr:read_telemetry` or `portalr:read_spend` on the tenant `X-Tenant` names. A caller whose key binds it to another tenant is refused first. Python can't stop other code calling `allowed()`: what keeps a `Tenant` unforgeable is the layering test, which fails if any module but the router imports it. A `Tenant` is read-only once made. The same test holds the readers and invitations to being the only code that sends HTTP.
- **Queries are built from typed parameters.**
  - An id from the request must match `[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}`, and is quoted as a Go string, which TraceQL, LogQL and PromQL all read. The tenant's id is grantr's, checked by grantr, and is quoted, not pattern-checked.
  - Each tool's tenant comes first in every query, under its own name: `span.tenant.id` in TraceQL; `tenant_id` structured metadata in LogQL; prom-label-proxy's `tenant_id` parameter; Langfuse's `traceTags=tenant:<id>`; LiteLLM's team `tenant-<id>`.
  - A test builds every query each reader can send, for every combination of its filters, and checks the tenant is there.
- **Tempo** finds traces with `/api/search` and reads one with `/api/v2/traces/<id>`. A trace it reads is shown only if one span names the tenant and none names another; any other trace, or none, answers `data: null`. A search can still list a trace that another tenant's span shares, since TraceQL matches spans, so its results leave out the root's service and name, which may be the other tenant's; reading the trace applies the rule.
- **Each reader checks its tool's answer as well as its query:** Langfuse's scores must carry their traces' tags, and only those tagged `tenant:<id>` are kept, in case Langfuse ignored the filter; LiteLLM's team must be `tenant-<id>`; Prometheus's selectors name `tenant_id` themselves, so a reader pointed at Prometheus directly, without the proxy, is still filtered.
- **Prometheus metrics are named, not written:** `turn_latency` (artifactr's turns, p95) and `failed_runs`, each a PromQL query whose selectors name the tenant, as the proxy also makes sure.
- **Invitations:** `SupabaseInvite` calls Supabase Auth's `/invite`. When the person has an account, Supabase answers 422 with `email_exists` or `user_already_exists`, and a magic link that is generated but not sent finds their user id; the link is discarded and never logged. The route refuses a caller bound to another tenant, checks `grantr:add_member` before Supabase is asked, and grantr checks it again when it adds the member. Inviting a member again succeeds and changes nothing. Supabase failing is 502, `invite_failed`. Without an `invite`, the route doesn't exist.
- **`config.json` takes only a publishable key:** `Site` refuses an `sb_secret_` key or a JWT whose role is `service_role`, since the file is public.
- **The router asks grantr through a protocol,** `portalr.fastapi.Grants`, which grantr's `Grants` satisfies; portalr still depends on `grantr[fastapi]`, for its callers and the deployment's resources. The protocol exists for the tests' shim: grantr's built-in roles don't yet place portalr's actions, since their `read_` rule would give every viewer portalr's reads, and `operator` none. Until grantr places them ([#91](https://github.com/alexnodeland/lattice/issues/91), which blocks phase 7), the router's tests answer portalr's actions as the RFC intends, over grantr's memberships and operators.
- **The OpenAPI document is `schemas/portalr.openapi.json`,** as the libraries' are, rather than the RFC's `portalr.v1.json`. A drift test holds it to the router, and `moon run portalr:schema` rewrites it.
- **Acceptance covers Langfuse and LiteLLM down.** Tempo, Loki, Prometheus and prom-label-proxy are light enough to run, up and down, in the Acceptance job. Langfuse and LiteLLM aren't. Their up path is proven by contract tests against stand-ins for their APIs, and by a reader check in the Smoke job's run of the full stack.

## Options considered

| Option | For | Against |
|---|---|---|
| **A read answers 200 with its tool's status (chosen)** | A card fails alone, and the UI says why | A client must read `status`, not the HTTP code |
| 503 when a tool is down | The usual HTTP meaning | Every card's error path is the same as a refused read's; Schemathesis counts it as the server's error |
| A `Tenant` any code can make from a string | Simpler | A reader could be handed a tenant grantr never allowed |
| PromQL from the UI, through the proxy | Any chart | The RFC's rule that no user writes a query; a malformed one costs Prometheus |

## Consequences

- Easier: every query portalr can send is in one module, under a test that checks its tenant.
- Easier: a tool that is down, or absent, shows as such on its own cards.
- Harder: Langfuse's and LiteLLM's real APIs are exercised only in Smoke. A change to them shows there, or in production.
- Harder: until grantr's roles place portalr's actions, an application that mounts the router gives every viewer portalr's reads. Phase 7 wires portalr into the template after that change ([#91](https://github.com/alexnodeland/lattice/issues/91)).
