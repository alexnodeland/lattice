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

`deploy/host/bootstrap` installs Docker with Compose, make, jq and uv, and refuses Docker before 28.0 or Compose before 2.24.4; rotates Docker's logs; lets in only the ports `sshd` listens on, HTTP and HTTPS through ufw; and writes `.env` with fresh secrets and the host's settings:

| Setting | Value |
|---|---|
| `STACKR_RECIPE` | `host`: `make` adds the overlay, `deploy/host/compose.prod.yaml`, and starts the `auth` profile |
| `STACKR_EDGE_BIND` | `0.0.0.0`: Caddy's 80 and 443 on every interface. Everywhere else it is `127.0.0.1`, unless you choose a LAN address on purpose |
| `STACKR_DATABASE` | `postgres` |
| `STACKR_DOMAIN` | The domain Caddy serves, as `app.<domain>` and `auth.<domain>` |
| `AUTH_PUBLIC_URL`, `AUTH_SITE_URL` | `https://auth.<domain>`, GoTrue's address and its tokens' issuer, and `https://app.<domain>` |

Keep a copy of `.env` off the host: it holds every secret, including the ones that encrypt Langfuse's and LiteLLM's data.

- **Email:** GoTrue sends invitations and password resets only through an SMTP server. Set `AUTH_SMTP_HOST`, `AUTH_SMTP_PORT`, `AUTH_SMTP_USER`, `AUTH_SMTP_PASSWORD` and `AUTH_SMTP_SENDER`.
- **Left to you:** hardening SSH (keys only, no password or root login), fail2ban, and unattended upgrades.

## Start it

```bash
sudo make up
sudo make smoke
```

On a host, `make` starts the `auth` profile with the others. Caddy gets the certificates the first time each name is asked for. `make smoke` checks the stack from inside its networks, and the edge: every service publishes on the loopback but Caddy, which publishes only at `STACKR_EDGE_BIND`; HTTP redirects to HTTPS; and GoTrue's admin API is refused at the edge.

To try the recipe on your own machine, leave `STACKR_EDGE_BIND` at `127.0.0.1` and use `CADDY_TLS="tls internal"`, as CI does: nothing is reachable from another machine.

## The application

Generate it with `hosting: host` ([The application template](template.md)). Its overlay, `deploy/host/compose.prod.yaml`, runs the image `APP_IMAGE` names, as its CI publishes it, publishes no port, and joins only the `stackr` network, where Caddy reaches it as `app:8000`. Its `.env` names the stack's services on that network:

| Setting | On a single host |
|---|---|
| `DATABASE_URL`, `DATABASE_ADMIN_URL` | The role it works as and the tables' owner, on `postgres:5432` |
| `AUTH_ISSUER` | `https://auth.<domain>` |
| `AUTH_JWKS_URL` | `http://gotrue:9999/.well-known/jwks.json`, which the overlay sets |
| `AUTH_ADMIN_URL` | `http://gotrue:9999`, which the overlay sets, since the edge refuses the admin API |
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

## Backups

Set `BACKUP_S3_*` in `.env` to a bucket off the host, on any S3-compatible store reached over HTTPS, then `make up` again, and `make backup` at once: it makes pgBackRest's stanza, starts PostgreSQL archiving its WAL there, and takes the first full backup ([ADR-0027](../adr/0027-the-single-hosts-backups.md)):

| Setting | What it is |
|---|---|
| `BACKUP_S3_ENDPOINT`, `BACKUP_S3_PORT` | The store's host name and HTTPS port, reached path-style |
| `BACKUP_S3_BUCKET`, `BACKUP_S3_REGION` | The bucket, and its region |
| `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | Keys that may read and write the bucket |
| `BACKUP_S3_CA_FILE` | The CA bundle on the host the store's certificate is checked against: the host's own, unless the store has a CA of its own |
| `BACKUP_CIPHER_PASS` | Encrypts PostgreSQL's backups. Without it they can't be restored: keep it, with the rest of `.env`, off the host |

ClickHouse's backups, Langfuse's traces, leave the host as they are: stackr doesn't encrypt them. Turn on the bucket's server-side encryption, as the AWS recipe's buckets have.

- **Nightly,** `stackr-backup.timer` runs `deploy/host/backup`: pgBackRest backs up PostgreSQL, a full backup on Sundays and a differential on the other nights, keeping two full backups and what they need; then ClickHouse backs itself up whole, as `clickhouse/<UTC time>`. Give the bucket a lifecycle rule that expires `clickhouse/` after the days you need. `make backup` runs it now.
- **Each Sunday,** after the backup, `stackr-restore-drill.timer` runs `deploy/host/restore-drill`: it writes a sentinel row, restores PostgreSQL's latest backup into a new container and ClickHouse's beside the live one, and checks the tables and the sentinel. `make restore-drill` runs it now.
- **Alerts:** Grafana alerts when no backup has succeeded in 36 hours, when the latest one failed, when the drill hasn't passed in eight days, and when the latest one failed. Add a contact point in Grafana for them to reach you; none is provisioned.
- **Not backed up:** Prometheus's data, 15 days of metrics; and `.env`, which you keep elsewhere yourself.

### Restoring

On a new host, with the same `.env` and the stack stopped:

1. **PostgreSQL:** remove the `postgres` volume's contents, then, in the `postgres` service's image, write pgBackRest's configuration and restore:

   ```bash
   docker compose -f compose.yaml -f deploy/host/compose.prod.yaml run --rm --no-deps --entrypoint sh postgres \
     -c 'pgbackrest-conf && gosu postgres pgbackrest --stanza=stackr restore'
   ```

2. **ClickHouse:** start only ClickHouse, before Langfuse, so its database is still empty, and restore the backup you choose as ClickHouse's `admin`, through the `backups` named collection. Neither Langfuse's user nor the `backup` user can write Langfuse's tables from the bucket, by design ([ADR-0031](../adr/0031-clickhouses-admin-apart-from-langfuse.md)).

   ```bash
   docker compose -f compose.yaml -f deploy/host/compose.prod.yaml up --detach --wait clickhouse
   docker compose -f compose.yaml -f deploy/host/compose.prod.yaml exec clickhouse sh -c \
     'CLICKHOUSE_USER=admin CLICKHOUSE_PASSWORD="$CLICKHOUSE_ADMIN_PASSWORD" clickhouse-client \
       -q "RESTORE DATABASE default FROM S3(backups, '\''<name>'\'')"'
   ```

3. `make up`.

## Update it

Check out the new stackr tag, then `make env` and `make up` again: `make env` adds any new setting, and Compose pulls the new images and recreates what changed. Langfuse, LiteLLM, GoTrue and the application migrate their databases when they start.

To use ClickHouse by hand, sign in as its `admin`, inside its container: `docker compose exec clickhouse sh -c 'CLICKHOUSE_USER=admin CLICKHOUSE_PASSWORD="$CLICKHOUSE_ADMIN_PASSWORD" clickhouse-client'`. Langfuse's user reaches only Langfuse's data ([ADR-0031](../adr/0031-clickhouses-admin-apart-from-langfuse.md)).
