# Task trackers

relayr's tracker connector lets rules' runs file work in a task tracker, and brings what people change there back into reflexr as `tracker:` events ([lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md), [relayr's guide](../../relayr/guides/trackers.md)). stackr runs the trackers beside the stack, from two opt-in recipes, Plane's Community edition and Vikunja; gives each tenant a tracker workspace and a tracker user of its own, by a checklist; and checks each tenant with `make tracker-check`. The template's `tracker` question wires an application to one ([The application template](template.md)). [ADR-0039](../adr/0039-the-task-trackers-recipes-checker-and-question.md) records how it is built.

| | Plane | Vikunja |
|---|---|---|
| Recipe | `trackers/plane/compose.yaml`: ten services, from about 1.7 GiB | `trackers/vikunja/compose.yaml`: one binary and PostgreSQL |
| A tenant's | Workspace, and a user who is a member of it | Top-level project, owned by its user |
| Provisioned | By hand, in Plane's web app: its API makes no workspaces, users, keys or webhooks | By a script, through Vikunja's API and its command line |
| Licence | AGPL-3.0-only | AGPL-3.0-or-later |

## Run a tracker

Start the stack first: `make up` creates the `stackr` network the trackers join. Then:

```bash
make tracker-up TRACKER=plane      # or TRACKER=vikunja
make tracker-down TRACKER=plane    # stops it, keeping its data
```

Each recipe is a Compose project of its own (`stackr-plane`, `stackr-vikunja`), reading stackr's `.env`, where `make env` has generated their secrets. Each publishes one port, at `STACKR_BIND` ([ADR-0006](../adr/0006-networks-and-published-ports.md)), and joins the `stackr` network with the services an application talks to:

| Setting | Default | What it is |
|---|---|---|
| `PLANE_PORT`, `PLANE_URL` | 3800, `http://localhost:3800` | Where Plane is published, and where people reach it: its links, sign-in and CORS |
| `PLANE_API_KEY_RATE_LIMIT` | `300/minute` | Each API key's limit, and so each tenant's; Plane's own default is 60. The template's `TRACKER_BUDGET` is 300 to match |
| `PLANE_WEBHOOK_HOSTS` | `app.stackr.internal` | The one host Plane sends webhooks to: the application's name on the `stackr` network. Plane refuses private addresses unless their host is listed, and this lists no more than it needs. It takes only a URL whose host has a dot in it, so an application generated with `tracker=plane` has this name there beside `app` |
| `PLANE_WORKER_CONCURRENCY` | 2 | Celery's worker processes, which deliver webhooks; Celery's default is one per CPU, 1.25 GiB on 16 of them |
| `VIKUNJA_PORT`, `VIKUNJA_URL` | 3456, `http://localhost:3456` | Where Vikunja is published, and where people reach it |
| `VIKUNJA_REGISTRATION` | `false` | Whether people may sign themselves up; the operator makes each tenant's user instead |

An application in its app profile reaches Plane at `http://plane-proxy` and Vikunja at `http://vikunja:3456`; Plane sends its webhooks to it at `http://app.stackr.internal:8000`, and Vikunja at `http://app:8000`. An application run with `make serve`, outside Docker, reaches them at their published ports, and gets no webhooks: its followers find each change at their next poll instead, thirty seconds later.

### What Plane's recipe leaves out

The recipe runs ten of the thirteen services Plane's own Compose file does, unmodified, at v1.4.2, pinned by tag and digest:

- **No object storage.** MinIO's image is no longer published on Docker Hub, so uploads and attachments don't work. relayr writes text alone.
- **No public pages and no live collaboration** (`space` and `live`). Work items, comments and the API work without them.
- **RabbitMQ 4.1**, not the 3.13 image Plane's file names, which stops at boot.
- **The proxy's certificate settings** are left unset: set but empty, they break its Caddyfile. It serves HTTP on its one published port; a single host's edge would serve it over HTTPS.
- **The worker waits for RabbitMQ to be healthy.** One started before it never takes a task until it is restarted.

### Setting up Plane

Open `PLANE_URL/god-mode/` and make the instance's admin, the operator. **Leave telemetry off**: Plane asks on that page, and the instance's settings can turn it off later. Plane's web app is then at `PLANE_URL`.

## Provision a tenant on Plane

Plane's Community edition makes workspaces, users, API keys and webhooks only through its web app, so a tenant is set up by hand, as the operator, and checked after. For a tenant `acme`:

1. **The workspace.** Create a workspace for the tenant, `acme`: its slug is what the credentials name.
2. **The tenant's user, `relayr-acme`.** Plane's Community edition can't make bot users, so it is an ordinary one. Invite `relayr-acme@<your domain>` to the workspace as a **Member**, never an Admin; sign up as that user, in a private window, and accept the invitation. One user per tenant, not one for the deployment: a Plane key reaches every workspace its user belongs to.
3. **Its projects.** Add `relayr-acme` as a Member to each project a workspace of the tenant's is bound to, and to no other. A project's id is in its address, `/<workspace>/projects/<id>/`.
4. **Its key.** Signed in as `relayr-acme`, create an API token in its profile's settings. Copy it: Plane shows it once. Sign out.
5. **The webhook.** As the operator, in the workspace's settings, add a webhook to `http://app.stackr.internal:8000/relayr/v1/trackers/acme/plane`, for **Work items** and **Work item comments**. Copy its secret key.
6. **Store them** in the application's settings, beside each tenant's gateway key:

   ```bash
   TRACKER_CREDENTIALS={"acme": {"base_url": "http://plane-proxy", "api_key": "plane_api_...", "webhook_secret": "plane_wh_...", "workspace": "acme"}}
   TRACKER_BINDINGS={"acme/main": {"project": "<the project's id>", "labels": ["lattice"]}}
   ```

   `TRACKER_CREDENTIALS` is a JSON object by tenant, as `LITELLM_TENANT_KEYS` is; a deployment on AWS points the application's resolver at its secrets instead. Keys and secrets never reach the ledger, logs or spans.

7. **Check it**, from stackr:

   ```bash
   make tracker-check TENANT=acme TRACKER=plane APP_ENV=../my-app/.env
   ```

The guide's rules hold only if nothing but relayr uses `relayr-acme`'s key: relayr tells its own writes from people's by the values it records, and a key used elsewhere looks like people.

### A webhook Plane switched off

Plane retries a delivery only when it can't connect or times out: five times, the first after ten minutes. Then it deactivates the webhook and emails whoever made it. A delivery the application refuses is logged as sent, and one to a host `PLANE_WEBHOOK_HOSTS` doesn't allow is logged in the worker and never retried (`docker compose -p stackr-plane logs plane-worker`).

Nothing is lost either way: a webhook only wakes a follower, and the follower's next poll finds every change. To turn it back on, fix what failed (the application down, or a host that isn't allowed), then open the webhook in the workspace's settings and enable it. `make tracker-check` shows the changes no webhook announced, which a webhook that is off is.

## Provision a tenant on Vikunja

Vikunja's users, projects, tokens and webhooks are all scriptable. Each tenant has a top-level project, owned by its user, `relayr-acme`; Vikunja's users are instance-wide, so this isolation is weaker than Plane's, and suits a deployment of one tenant, or a few that trust each other. With `jq`, and a password of the operator's choosing:

```bash
cd packages/stackr
TENANT=acme PASSWORD=<a password> VIKUNJA=http://localhost:3456/api/v1
docker compose -p stackr-vikunja exec vikunja /app/vikunja/vikunja user create \
  --username "relayr-$TENANT" --email "relayr-$TENANT@example.com" --password "$PASSWORD"
session=$(curl -fsS "$VIKUNJA/login" -H 'Content-Type: application/json' \
  -d "{\"username\": \"relayr-$TENANT\", \"password\": \"$PASSWORD\"}" | jq -r .token)
auth=(-H "Authorization: Bearer $session" -H 'Content-Type: application/json')
project=$(curl -fsS -X PUT "$VIKUNJA/projects" "${auth[@]}" -d "{\"title\": \"$TENANT\"}" | jq -r .id)
expires=2027-01-01T00:00:00Z SECRET=$(openssl rand -hex 32)
curl -fsS -X PUT "$VIKUNJA/tokens" "${auth[@]}" -d '{"title": "relayr", "expires_at": "'"$expires"'",
  "permissions": {"tasks": ["create", "read_one", "read_all", "update"],
    "tasks_comments": ["create", "read_all"], "labels": ["create", "read_all"],
    "tasks_labels": ["create", "delete"], "projects": ["read_all"],
    "projects_webhooks": ["read_all"], "other": ["user"]}}' | jq -r .token
curl -fsS -X PUT "$VIKUNJA/projects/$project/webhooks" "${auth[@]}" \
  -d '{"target_url": "http://app:8000/relayr/v1/trackers/'"$TENANT"'/vikunja", "secret": "'"$SECRET"'",
    "events": ["task.created", "task.updated", "task.deleted", "task.comment.created"]}'
```

The token's scopes are what relayr needs, and what `make tracker-check` reads with:

| Scope | For |
|---|---|
| `tasks`: `create`, `read_one`, `read_all`, `update` | Filing and changing items, and reading them back |
| `tasks_comments`: `create`, `read_all` | Comments, both ways |
| `labels`: `create`, `read_all`; `tasks_labels`: `create`, `delete` | Labels, found or made by name |
| `projects`: `read_all`; `projects_webhooks`: `read_all`; `other`: `user` | `make tracker-check`: the user's projects, their webhooks, and whose the token is |

Vikunja's tokens must expire, and can't read their own expiry, so the credentials keep it, as `expires_at`, for the checker; the application doesn't read it:

```bash
TRACKER_CREDENTIALS={"acme": {"base_url": "http://vikunja:3456", "api_key": "tk_...", "webhook_secret": "<SECRET>", "expires_at": "2027-01-01T00:00:00Z"}}
TRACKER_BINDINGS={"acme/main": {"project": "<the project's id>"}}
```

Then `make tracker-check TENANT=acme TRACKER=vikunja APP_ENV=../my-app/.env`.

## Check a tenant

`make tracker-check` reads the application's `TRACKER_CREDENTIALS` and `TRACKER_BINDINGS` (from `APP_ENV`, or the environment), and asks the tracker about each step, with the tenant's own key and GET requests only. It changes nothing.

```text
ok: the key is relayr-acme's
ok: relayr-acme is a member of workspace acme
ok: relayr-acme is a member of project Ops
ok: relayr-acme is not in globex's workspace, globex
skip: Plane's API keys can't read webhooks: check it in the workspace's settings, ...
ok: every change in the last hour came with its webhook
```

| It checks | On Plane | On Vikunja |
|---|---|---|
| The key | Works, and is `relayr-<tenant>`'s | Works, and is `relayr-<tenant>`'s |
| Membership | An ordinary member of the tenant's workspace, and of each bound project | Each bound project is the user's |
| Isolation | A member of no project that isn't bound, and refused in every other tenant's workspace the credentials name | Sees no project another user owns, such as one shared with it |
| The webhook | Not readable with an API key: it says so | Each bound project's webhook goes to the application's route, with relayr's events |
| Expiry | | Warns 14 days before `expires_at` |
| Nudges | `relayr.trackers.unnudged` for the tenant, from Prometheus, over the last hour | The same |

A missing step, or broken isolation, fails it, with exit status 1; a warning doesn't. Isolation is as far as the API shows it: Plane's API keys list no user's workspaces, so the checker asks for each other tenant's in turn, and a workspace no credentials name can't be asked about.

The nudges are read when the `observability` profile runs and the application exports its metrics: relayr's follower counts each change a poll found that no webhook announced, and the Collector labels it with the tenant. Changes with no webhook mean it isn't registered, is off, or goes to a host the tracker refuses. With no Prometheus, or no change counted yet, the checker says it couldn't tell.

## Rotation

- **A key, without a gap.** Make a second key for the same user (Plane: another API token; Vikunja: another token, with its expiry), put it in `TRACKER_CREDENTIALS`, restart the application, and revoke the first once `make tracker-check` passes. The template reads `TRACKER_CREDENTIALS` when it starts; a resolver over a secrets store is asked again every five minutes, and at once when the tracker refuses a key.
- **Vikunja's tokens expire**, so rotate each before `make tracker-check` warns of it.
- **A webhook's secret** changed in the tracker before it is stored costs only nudges: until the application has it, its webhooks are refused and its followers poll.

## Offboarding a tenant

1. Remove the tenant from `TRACKER_BINDINGS` and `TRACKER_CREDENTIALS`, and restart the application: its followers stop.
2. Shut `relayr-<tenant>` out of the tracker (Plane: delete its API tokens and remove it from the workspace; Vikunja: `vikunja user change-status --disable` with its id, which `vikunja user list` shows), and delete the tenant's webhook.
3. Delete its rows from relayr's tracker tables, titles and descriptions among them, as the tables' owner, in the application's schema:

   ```sql
   DELETE FROM relayr_tracker_items WHERE tenant_id = 'acme';
   DELETE FROM relayr_tracker_snapshots WHERE tenant_id = 'acme';
   DELETE FROM relayr_tracker_followers WHERE tenant_id = 'acme';
   DELETE FROM relayr_tracker_dead_letters WHERE tenant_id = 'acme';
   ```

relayr never deletes tracker data. The workspace is the tenant's, exported and deleted by the operator under the deployment's retention policy.

## Licences

Plane's Community edition is AGPL-3.0-only, and Vikunja AGPL-3.0-or-later. lattice stays MIT: the recipes run their unmodified images, and relayr calls their REST APIs, and never vendors, patches or links their code, as stackr already runs Grafana, Loki and Tempo. Each recipe's `NOTICE.md` names every image it runs, with its licence and source. A deployment that modifies either tracker takes on the AGPL's obligations for it. This is a reading, not legal advice.
