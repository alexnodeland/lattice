# ADR-0026: The single host

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds phase 2 of [RFC-0004](../rfcs/0004-hosting-recipes.md), the single host, but for its backups and restore drill, which follow in their own pull request. Records what the RFC left to the build.

## Context

RFC-0004 runs stackr's Compose stack on one VM behind Caddy, on the `postgres` adapter with GoTrue alone for identity, and asks that `make smoke` and `make smoke-app` pass through the edge in CI. Four things weren't settled: how `make` chooses the overlay, where GoTrue keeps its data and keys, how the smoke test reaches services whose ports the overlay removes, and how a generated application joins the host.

## Decision

- **`STACKR_RECIPE`, `local` or `host`, chooses the overlay.** With `host`, `make` runs Compose with `-f compose.yaml -f deploy/host/compose.prod.yaml`, passes the same files to `scripts/smoke`, and starts the `auth` profile with the others. It refuses `host` on the `supabase` adapter or without `auth`, and the `auth` profile beside local Supabase. `deploy/host/bootstrap` sets it, with the domain and GoTrue's addresses.
- **Nothing is reachable from another machine unless chosen.** Caddy publishes at `STACKR_EDGE_BIND`, 127.0.0.1 by default, as every other port publishes at `STACKR_BIND`; an operator sets a LAN address or 0.0.0.0 on purpose, and `bootstrap` sets 0.0.0.0 on the host users reach. The admin UIs are pinned to 127.0.0.1 whatever `STACKR_BIND` says. `make smoke` checks both.
- **The host's own defences.** `bootstrap` refuses Docker before 28.0, which lets machines on the same link reach ports published on 127.0.0.1, and Compose before 2.24.4, which lacks `!reset` and `!override`. It lets through ufw only the ports `sshd` listens on, and refuses to turn ufw on if it can't tell them, with 80 and 443; and it rotates Docker's logs. Hardening SSH, fail2ban and unattended upgrades are the operator's.
- **The edge's headers:** HSTS, `X-Content-Type-Options: nosniff`, a `Referrer-Policy`, and no `Server`. HTTP/3 is off, since it would need 443/udp published and let through ufw. Caddy replaces each client's `X-Forwarded-For` with its address, and GoTrue's per-address rate limits read it (`GOTRUE_RATE_LIMIT_HEADER`): without that header, GoTrue v2.197.0 applies none.
- **One domain, two names.** `STACKR_DOMAIN` gives `app.<domain>`, the template's `app` service at `app:8000`, and `auth.<domain>`, GoTrue. Caddy's `CADDY_TLS` is empty for Let's Encrypt, or `tls internal` for its own CA, as CI runs it. On the stack's network, Caddy also answers to both names, so a container reaching a public name stays inside.
- **GoTrue has its own database, `auth`,** owned by a `gotrue` role that `db-init` creates, whose `auth` schema it migrates, and which no other role may connect to. Its migrations grant to a `postgres` role, which plain PostgreSQL has. Its image is pinned by digest. Its email goes through the optional `AUTH_SMTP_*` settings; without them it sends none, so invitations and password resets need them.
- **`make env` makes GoTrue's keys:** an ES256 key set (`AUTH_JWT_KEYS`) and the service role's key (`AUTH_SERVICE_ROLE_KEY`), a JWT signed with it, by `scripts/_auth_keys.py` with cryptography and PyJWT. `setup-env` generates them once, as it does every secret, and makes the service role's key again when the key set no longer has its key. That key is valid for ten years and can't be revoked on its own: replacing the key set is the only way, and ends every token signed with the old one. GoTrue's required `AUTH_JWT_SECRET` is a random value no one signs with.
- **The smoke test's requests run in a `probe` container,** curl on the stack's networks, in the `smoke` profile beside `telemetrygen`. Every check reaches its service by name, on one machine and on a host alike, so the overlay can remove the ports nothing outside needs. Its settings follow Compose's order: the environment, then `.env`, then `.env.example`. With Caddy's own CA, the probe trusts that root, copied out of Caddy's container, and nothing else.
- **The admin API has its own setting.** The template's admin commands call `AUTH_ADMIN_URL`, or `AUTH_ISSUER` when it is unset, so they reach GoTrue at `http://gotrue:9999` while the edge refuses `/admin/*`. The application's host overlay sets it, and `make smoke-app` names the tenant's owner by email so the command finds them that way.
- **A `hosting` question, `none` by default.** `host` adds `deploy/host/compose.prod.yaml` to the application: its published image (`APP_IMAGE`), no published port, and only the `stackr` network. `make smoke-app` generates it so on a single host, and checks it through Caddy.

### Where this departs from RFC-0004

- **A database of GoTrue's own, not an `auth` schema beside the application's tables.** It keeps identity out of [ADR-0022](0022-row-level-security-in-the-template.md)'s row-level security and the application's roles.
- **`scripts/_auth_keys.py`, a module, not a `scripts/auth-keys` command.** `make env` is its only caller on a host. The AWS recipe's one-off task (phase 3) gets a command around the same module, in its thin image.
- **No check yet that GoTrue's version follows the Supabase CLI's.** It needs the CLI's image pins, which `make validate` can't fetch offline: [#132](https://github.com/alexnodeland/lattice/issues/132).
- **The application reads GoTrue's key set at its private address,** `http://gotrue:9999/.well-known/jwks.json`, not through the edge: no certificate to trust inside the stack, and the same keys.
- **Signing up is off by default** (`AUTH_DISABLE_SIGNUP`): users are created through the admin API, by an application's admin commands or portalr's invitations.

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
