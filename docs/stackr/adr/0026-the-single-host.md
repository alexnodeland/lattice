# ADR-0026: The single host

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds phase 2 of [RFC-0004](../rfcs/0004-hosting-recipes.md), the single host, but for its backups and restore drill, which follow in their own pull request. Records what the RFC left to the build.

## Context

RFC-0004 runs stackr's Compose stack on one VM behind Caddy, on the `postgres` adapter with GoTrue alone for identity, and asks that `make smoke` and `make smoke-app` pass through the edge in CI. Four things weren't settled: how `make` chooses the overlay, where GoTrue keeps its data and keys, how the smoke test reaches services whose ports the overlay removes, and how a generated application joins the host.

## Decision

- **`STACKR_RECIPE`, `local` or `host`, chooses the overlay.** With `host`, `make` runs Compose with `-f compose.yaml -f deploy/host/compose.prod.yaml`, and passes the same files to `scripts/smoke`. It refuses `host` on the `supabase` adapter, and the `auth` profile beside local Supabase. `deploy/host/bootstrap` sets it, with the domain and GoTrue's addresses.
- **One domain, two names.** `STACKR_DOMAIN` gives `app.<domain>`, the template's `app` service at `app:8000`, and `auth.<domain>`, GoTrue. Caddy's `CADDY_TLS` is empty for Let's Encrypt, or `tls internal` for its own CA, as CI runs it. On the stack's network, Caddy also answers to both names, so a container reaching a public name stays inside.
- **GoTrue has its own database, `auth`,** owned by a `gotrue` role that `db-init` creates, whose `auth` schema it migrates. Its migrations grant to a `postgres` role, which plain PostgreSQL has.
- **`make env` makes GoTrue's keys:** an ES256 key set (`AUTH_JWT_KEYS`) and the service role's key (`AUTH_SERVICE_ROLE_KEY`), a JWT signed with it, by `scripts/_auth_keys.py` with cryptography and PyJWT. `setup-env` generates them once, as it does every secret. GoTrue's required `AUTH_JWT_SECRET` is a random value no one signs with.
- **The smoke test's requests run in a `probe` container,** curl on the stack's networks, in the `smoke` profile beside `telemetrygen`. Every check reaches its service by name, on one machine and on a host alike, so the overlay can remove the ports nothing outside needs. Its settings follow Compose's order: the environment, then `.env`, then `.env.example`. With Caddy's own CA, the probe trusts that root, copied out of Caddy's container, and nothing else.
- **The admin API has its own setting.** The template's admin commands call `AUTH_ADMIN_URL`, or `AUTH_ISSUER` when it is unset, so they reach GoTrue at `http://gotrue:9999` while the edge refuses `/admin/*`.
- **A `hosting` question, `none` by default.** `host` adds `deploy/host/compose.prod.yaml` to the application: its published image (`APP_IMAGE`), no published port, and only the `stackr` network. `make smoke-app` generates it so on a single host, and checks it through Caddy.

## Options considered

| Option | For | Against |
|---|---|---|
| **Requests from a probe container (chosen)** | No published port needed, on one machine or a host; the overlay stays as the RFC designs it | A container per request makes the smoke test slower |
| Keep every port on `127.0.0.1` on the host | No change to the smoke test | Every backend stays one tunnel away from anyone with a shell on the host, against the RFC's overlay |
| A CI-only file that publishes them again | No change to the smoke test | CI would test something other than the host |
| **GoTrue in a database of its own (chosen)** | Its tables and migrations apart from Langfuse's, LiteLLM's and the application's | One more database for `db-init` |
| GoTrue's `auth` schema in the application's database | One database | Ties identity to one application's database and its row-level security |

## Consequences

- Easier: `make smoke` and `make smoke-app` run the same way on one machine and on a host, and CI checks the host with Caddy's own CA.
- Easier: the `postgres` adapter has identity, so an application runs end to end without local Supabase.
- Harder: each smoke check starts a container.
- Next: the host's backups and their restore drill, RFC-0004's phase 2, in their own pull request.
