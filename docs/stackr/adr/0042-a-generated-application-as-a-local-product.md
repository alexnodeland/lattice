# ADR-0042: A generated application as a local product: one origin, a first run, and the tailnet

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland

Makes `make up` in a generated application give a working portal with chat, on the stack as it runs on one machine, and reachable from a person's other devices on their tailnet. Amends [ADR-0038](0038-portalr-in-the-template.md), whose portal signed in to Supabase from the browser.

## Context

ADR-0038 put portalr in the template, and the smoke test runs it, but a person following the README hit four walls, found by generating an application and running it beside a stack on one machine:

- **The UIs weren't served.** `.env.example` has an empty `PORTAL_UI_DIR`, for `make serve`. `make env` copies it to `.env`, Compose's `env_file` puts it in the container, and the empty value replaced the image's `/ui`, so `/portalr/app/` answered "this UI isn't built". The smoke test wrote its own `.env` and never saw it. This is a fix, not a decision: Compose sets `PORTAL_UI_DIR` over `.env`, as it sets `APP_HOST`, and the smoke test now writes its `.env` over `.env.example`.
- **The browser signed in to Supabase directly,** at `PORTAL_SUPABASE_URL` (`http://127.0.0.1:54321`). From another device that address is the device's own, and on stackr's PostgreSQL adapter there is no Supabase gateway at all: GoTrue alone serves `/token`, not the `/auth/v1/token` supabase-js asks for (`scripts/smoke` skipped the portal's scenarios there for this reason).
- **A new person has nothing.** Signing in works, and then the app says "There is no workspace here you can open": no tenant, no operator, and no workspace. A workspace is listed when grantr knows it, which it does once something is granted on it. Getting there took a user made through the admin API, `make operator`, `make tenant`, and a grant through grantr's API.
- **Reaching it from another device** needs an address other than `127.0.0.1`, and the owner's rule is that local stacks bind `127.0.0.1` only, never the LAN by default, never the internet.

## Decision

- **The portal signs in on the application's own origin.** `PORTAL_SUPABASE_URL=/`, now `.env.example`'s default, makes `config.json` name this origin, and the application passes Supabase Auth's three sign-in calls on: `POST /auth/v1/token`, `GET /auth/v1/user` and `POST /auth/v1/logout`, the ones portalr's UIs make and the only ones a single host's edge passes (ADR-0038). It matches them by path and method as routes, so nothing else under `/auth/v1` is served: not the admin API, not sign-up, not a changed user. The upstream URL is a constant per route, never built from the request's path, so no spelling of a path reaches another one, the failure ADR-0038's edge found in its first version. It sends the query, the body and three headers (`apikey`, `authorization`, `content-type`), and returns the status, the body and two headers (`content-type`, `cache-control`); none is logged. The upstream is where the deployment's commands find people, `AUTH_ADMIN_URL` or `AUTH_ISSUER`: `stackr.env` names local Supabase's gateway on the stack's network, and `STACK_AUTH_ADMIN_URL=http://gotrue:9999` names GoTrue on the PostgreSQL adapter. The browser then reaches one origin, so the content security policy's `connect-src` is `'self'` alone, and there is no CORS. An absolute `PORTAL_SUPABASE_URL` still works as before, and a single host's overlay still sets one, `https://app.<domain>`, where the edge passes the calls itself.
- **The three calls are passed on as Supabase Auth would answer them, and no more.** They are unauthenticated by design, as Supabase Auth's own are: the token call is how a person gets a token. A body over 64 KiB is refused (413) before anything is sent. The client's address isn't forwarded, so GoTrue's rate limits on sign-in count every person reaching the application as one, which on a tailnet is the people a person shares it with.
- **The portal reads a workspace's tracker items on this origin.** With a tracker, the application mounts relayr's tracker reads at their own `/relayr/v1` paths, and the portal's `Site` names them (`Surfaces(relayr="")`), so the app shows what a workspace filed. relayr's `tracker_reads_router` resolves who asks as reflexr's routes do: `automation.py`'s resolver, once private, is now its public `resolve_actor`, which `tracking.py` is given.
- **`make first-run EMAIL=...` is the first person in,** a command over the pieces the template had (`first_operator`, `provision_tenant`, `grant`). It makes the person's account in Supabase Auth if they have none, through the admin API with the email confirmed and a password it asks for twice and never shows; makes them the deployment's operator if it has none; creates a tenant they own (`TENANT`, `home` by default); and gives them a workspace in it to administer (`WORKSPACE`, `main`) if they can't open it yet, which names the workspace to grantr, so the app lists it. Each step is skipped once done, so it can run again, and it repairs a tenant made without the workspace. `EMAIL` may be an existing user's id instead, for whom no account is made.
- **`make tailnet` serves the application on the machine's tailnet name,** over HTTPS, with `tailscale serve`, for the tailnet only: never `tailscale funnel`. One handler, `/` to the application on `127.0.0.1`, is all it needs, since the portal signs in on the application's own origin. It changes the one HTTPS port it is given (`TAILNET_PORT`, 443), refuses a port something else is served on, or that Funnel puts on the internet, and `make tailnet-off` removes only what it set up there, Funnel included if someone turned it on. tailscale's own output is shown, since it says when the machine must first allow Serve or HTTPS. It finds the CLI on the PATH or in the macOS app, and installs nothing. Its ports stay on `127.0.0.1`: Tailscale reaches them there.

## Options considered

### Where the portal signs in

| Option | For | Against |
|---|---|---|
| **The application passes three calls (chosen)** | One origin wherever the application is reached; works with GoTrue alone; no setting changes between this machine and a tailnet | The application carries a small proxy, which its tests hold to the three calls |
| The browser calls Supabase directly (ADR-0038's local default) | Nothing in the application | Breaks on every origin but this machine's, and on the PostgreSQL adapter |
| `tailscale serve` maps `/auth/v1/...` to Supabase | No code | Only on the tailnet, only with Supabase's gateway (GoTrue alone has no `/auth/v1`), and this machine's own origin still needs another answer |
| Caddy in front of the application locally, as on a single host | The edge's tested allow-list | A second service and a second port for every local run |

### The first person in

| Option | For | Against |
|---|---|---|
| **A command, over grantr's existing pieces (chosen)** | Deliberate; runs again safely; no request path changes | A terminal step before the first sign-in |
| The first person to sign in becomes the operator and owner | No step at all | Whoever signs in first owns the deployment, and every request pays a check for a moment that happens once |
| A configured email is claimed at its first sign-in | No terminal step after configuring it | A check on every request's path for the same once, and the account still has to be made, which the UIs don't offer: they sign in only, and an invitation's link has no page to set a password |

### Reaching it from other devices

| Option | For | Against |
|---|---|---|
| **`tailscale serve` (chosen)** | The tailnet's own identity and HTTPS; nothing binds beyond `127.0.0.1`; installs nothing | Needs Tailscale on the machine and the devices |
| `APP_BIND=0.0.0.0` | Already there | The LAN, unauthenticated, and plain HTTP |
| `tailscale funnel` | Any device | The internet: never |

## Consequences

- Easier: a generated application, beside the stack on either adapter, goes from `make up` and `make first-run` to a signed-in portal with chat, on this machine and on a tailnet, with no setting changed between them.
- Easier: the portal's scenarios could run on the PostgreSQL adapter too, which `scripts/smoke` still skips; that is left for later.
- Harder: the application now proxies three calls, which its tests pin, and which must follow supabase-js if portalr's UIs ever make another.
- Not done: invitations still go to Supabase's gateway (`PORTAL_AUTH_URL`), so they don't work with GoTrue alone, and an invited person has no page to set a password; WordCraft's editor isn't in the template yet, and when it is, its own origin needs a second tailnet port (portalr ADR-0049).
