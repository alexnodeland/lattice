# A single host

stackr's stack on one VM, shaped for production: Caddy is the only service the internet reaches, PostgreSQL and GoTrue replace local Supabase, and the admin UIs stay behind SSH. It is the first of [RFC-0004](../rfcs/0004-hosting-recipes.md)'s two recipes; [ADR-0026](../adr/0026-the-single-host.md) records how it is built.

| Port | On a single host |
|---|---|
| Database | The `postgres` profile, PostgreSQL 17 |
| Identity | GoTrue, the `auth` profile, at `https://auth.<domain>` |
| Everything else | As on one machine: the Collector, LiteLLM, Langfuse, MinIO |

## Prepare the host

On a VM running Ubuntu 24.04, with `app.<domain>` and `auth.<domain>` pointing at it:

```bash
git clone --branch stackr-v<version> https://github.com/alexnodeland/lattice
cd lattice/packages/stackr
sudo deploy/host/bootstrap example.com
```

`deploy/host/bootstrap` installs Docker with Compose, make, jq and uv; lets in only SSH, HTTP and HTTPS through ufw; and writes `.env` with fresh secrets and the host's settings:

| Setting | Value |
|---|---|
| `STACKR_RECIPE` | `host`: `make` adds the overlay, `deploy/host/compose.prod.yaml` |
| `STACKR_DATABASE` | `postgres` |
| `STACKR_DOMAIN` | The domain Caddy serves, as `app.<domain>` and `auth.<domain>` |
| `AUTH_PUBLIC_URL`, `AUTH_SITE_URL` | `https://auth.<domain>`, GoTrue's address and its tokens' issuer, and `https://app.<domain>` |

Keep a copy of `.env` off the host: it holds every secret, including the ones that encrypt Langfuse's and LiteLLM's data.

## Start it

```bash
sudo make up PROFILES="observability langfuse gateway auth"
sudo make smoke PROFILES="observability langfuse gateway auth"
```

Caddy gets the certificates the first time each name is asked for. `make smoke` checks the stack from inside its networks, and the edge from the outside: only Caddy publishes on a public interface, HTTP redirects to HTTPS, and GoTrue's admin API is refused at the edge.

## The application

Generate it with `hosting: host` ([The application template](template.md)). Its overlay, `deploy/host/compose.prod.yaml`, runs the image `APP_IMAGE` names, as its CI publishes it, publishes no port, and joins only the `stackr` network, where Caddy reaches it as `app:8000`. Its `.env` names the stack's services on that network:

| Setting | On a single host |
|---|---|
| `DATABASE_URL`, `DATABASE_ADMIN_URL` | The role it works as and the tables' owner, on `postgres:5432` |
| `AUTH_ISSUER` | `https://auth.<domain>` |
| `AUTH_JWKS_URL` | `http://gotrue:9999/.well-known/jwks.json`, through `STACK_AUTH_JWKS_URL` |
| `AUTH_ADMIN_URL` | `http://gotrue:9999`, since the edge refuses the admin API |
| `AUTH_SERVICE_ROLE_KEY` | stackr's `AUTH_SERVICE_ROLE_KEY` |

Before it first starts, create the role it works as, then start it:

```bash
docker compose -f compose.yaml -f deploy/host/compose.prod.yaml --profile app run --rm app <slug>-admin db-roles
docker compose -f compose.yaml -f deploy/host/compose.prod.yaml --profile app up --detach --wait
```

## Reach the admin UIs

Grafana, Langfuse, LiteLLM's admin UI and MinIO's console listen on the host's `127.0.0.1` only. Forward them over SSH:

```bash
ssh -L 3000:127.0.0.1:3000 -L 3300:127.0.0.1:3300 -L 4400:127.0.0.1:4400 <the host>
```

Then open <http://localhost:3000>, <http://localhost:3300> and <http://localhost:4400/ui> as you would on one machine. `make tenant` runs on the host itself, against LiteLLM's port there.

## Update it

Check out the new stackr tag, then `make up` again: Compose pulls the new images and recreates what changed. Langfuse, LiteLLM, GoTrue and the application migrate their databases when they start.
