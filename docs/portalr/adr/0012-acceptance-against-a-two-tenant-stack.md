# ADR-0012: Acceptance against a two-tenant stack

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Phase 4's exit criterion is that portalr's Bruno collection passes against an application on the stack, with each tool up and down, and that reading as one of two tenants never shows the other's telemetry. [lattice ADR-0015](../../adr/0015-acceptance-tests-against-the-reference-applications.md) runs each library's `api` task in CI's Acceptance job against its reference application. portalr has no reference application of its own: the template wires it into one in phase 7. [ADR-0011](0011-the-router-and-its-readers.md) leaves Langfuse and LiteLLM out of the Acceptance job, and answers portalr's actions with a test shim until grantr's roles place them, which [grantr ADR-0023](../../grantr/adr/0023-portalrs-admin-reads.md) has since done.

## Decision

`moon run portalr:api` (`scripts/api`) runs portalr's acceptance tests against a test application, beside the stack's tools, in a compose project of its own.

- **The test application is a fixture,** `tests/app/`: `portalr_router` mounted at `/portalr`, over an in-memory grantr whose seed makes `ops` an operator, `alice` acme's owner, `carol` globex's and `bob` a member of acme. It trusts an `x-user` header for its caller, and invites by an email's local part. It reads its tools' URLs from `PORTALR_*_URL`, and names a Langfuse and a LiteLLM that aren't there, so their reads are unavailable.
- **The tools are stackr's:** `compose.yaml` runs Tempo, Loki, Prometheus and prom-label-proxy from stackr's `deploy/` configuration, on ports the system picks, so the run can't collide with a running stack.
- **The two-tenant test seeds the tools directly** (`acceptance/`), with OTLP to Tempo, Loki and Prometheus: a trace, a log record and a failure series for each of acme and globex, and a trace that an acme span and a globex span share. Then it reads as each through portalr's readers. Tempo finds each tenant's traces, and shows neither the shared trace; Loki answers each tenant's own record; Prometheus, through the proxy, answers each tenant's own rate.
- **The Bruno collection runs twice:** `up/` with every tool up, after the seed, then `down/` after Tempo, Loki and the proxy stop, when each read answers `unavailable` and the request still succeeds. It also checks the refusals: a member, another tenant, and an owner asking for the deployment.
- **Schemathesis runs over `schemas/portalr.openapi.json`** as an owner, without its `positive_data_acceptance` check, since grantr rightly refuses the tenants it makes up.
- **The router takes grantr's `Grants`.** The shim is gone, and with it the `portalr.fastapi.Grants` protocol that served it: the router's tests run against grantr's own roles. This amends ADR-0011.
- **The wheel carries the built UIs.** Vite writes `app` and `admin` into `src/portalr/static/`, which git ignores; portalr's `build` depends on theirs, and a `ui-in-wheel` check, in `check`, fails unless the wheel holds both indexes. The release workflow builds them before it builds portalr.

## Options considered

| Option | For | Against |
|---|---|---|
| **A test application beside the stack's tools (chosen)** | Runs in the Acceptance job's budget; seeds exactly two tenants | Not the template's wiring, which phase 7 tests |
| The full stack from stackr's compose | The real thing | Langfuse and LiteLLM are too heavy for the job (ADR-0011) |
| Seeding through artifactr's and reflexr's telemetry | Tests the libraries' attributes too | Needs the collector and a run of each library; stackr's Smoke job already covers that path |
| Keeping the `Grants` protocol | Another grants implementation could stand in | Nothing does; it only served the shim |

## Consequences

- Easier: the readers' tenant filters run against the real tools in CI, on every change to portalr or stackr's configuration.
- Easier: a down tool shows as unavailable on its own route, tested.
- Harder: `portalr:api` needs Docker, and builds the test application's image.
- Harder: the test application is a second wiring of the router to keep in step with the template's, until phase 7 tests that one too.
