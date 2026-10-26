# Upgrading to 0.2

What changes for an application on lattice's 0.1 releases, and what to do. The packages are released one by one: lattice-core 0.2, then grantr 0.2, artifactr 0.3 and reflexr 0.2, then relayr 0.2, then portalr 0.2, then stackr 0.2. evalr is unchanged.

Three changes break what a client or an application of its own may rely on: `ask_user`'s questions and answers on the wire, the errors of a rule reflexr refuses, and two methods a `Storage` of your own must add. An application built from stackr's template, with lattice's own storages and portalr's UIs, has nothing to change for any of them.

## On the wire: `ask_user`'s questions and answers

`ask_user` asks one to four questions with options now ([#423](https://github.com/alexnodeland/lattice/pull/423)), and an answer to it is one of two shapes ([artifactr ADR-0083](artifactr/adr/0083-ask-user-asks-questions-with-options.md)):

```json
{"answers": [{"selected": ["Weekly"]}, {"selected": [], "other": "Every other Tuesday"}]}
```

```json
{"reply": "Whatever you think is best"}
```

The question changed too: `ask_user(question, choices)` is now `ask_user(questions)`, a list of `Question`s, so a client that draws a `run_paused` request's `args` reads `questions`, not `question` and `choices`.

An `answer_deferred` that sends a plain string, as 0.1's clients did, is refused with `validation_failed`, over the WebSocket and REST alike. A client of artifactr's protocol of its own must send one of the two shapes; portalr's chat does. A run paused on a question asked before the upgrade, whose request still holds `question` and `choices`, is answered only by a reply: a message in its thread, or `{"reply": ...}`, so it isn't stranded.

## reflexr: a refused rule's errors name their field

The `errors` of a `validation_failed` for a stored rule were strings. Each is now an object, `{loc, msg, type}`, as Pydantic reports a field's error, on REST, the stream protocol and MCP alike, and in `ValidationFailed.errors` for a Python caller ([#723](https://github.com/alexnodeland/lattice/pull/723)):

```json
{"loc": ["rule", "when", "throttle"], "msg": "...", "type": "missing"}
```

- **`loc`** is always there: the path to the field, its names and a list's items by number (`str | int`), starting with `rule`, as Pydantic's paths into a command do. A problem that names no field, such as a filter's unknown event type or predicate, a `matches` operator, the rule's size or its provenance, has an empty `loc`.
- **`msg`** is the message the string was.
- **`type`** is Pydantic's name where it has one (`missing`, `string_too_long`, `less_than_equal`, or a params field's own), else reflexr's: `not_allowed`, `too_large` or `unknown`.

A client that showed each error as a string shows its `msg`. portalr's rule editor already reads `loc`, and names the field. `reflexr.core.Problem`, what `InvalidRule.problems`, `check_stored` and relayr's `check_draft` hold, is still a `str` of the message, so a Python caller that compares or joins them is unchanged.

## A `Storage` of your own: `renew_lease` and `drop_revisions`

artifactr's `Storage` protocol gains two required methods ([the storage guide](artifactr/guides/storage.md#writing-your-own)). `InMemoryStorage` and `SqlStorage` have both, so an application on either has nothing to do; a storage written outside artifactr must add them, or it no longer satisfies the protocol.

- **`renew_lease(scope, key, holder, ttl) -> bool`** ([#692](https://github.com/alexnodeland/lattice/pull/692), an amendment of [artifactr ADR-0055](artifactr/adr/0055-turns-from-the-log.md)). It renews a lease only while it is still this holder's, expired or not, and never takes one, checking and renewing in one statement: in SQL, an `UPDATE … WHERE holder = :holder`; in memory, under the workspace's lock. It returns whether it renewed. If another holder took the lease after it expired, even one that has since released it, it renews nothing and returns `False`. A thread's claim calls it when its timer finds a renewal overdue, as after a stall of the event loop, so a holder whose loop stalled keeps its run while storage still has the lease as its own. Holders must be unique to each claim attempt, as the runner's `new_id("claim")` are.
- **`drop_revisions(scope, artifact_id, versions) -> int`** ([#730](https://github.com/alexnodeland/lattice/pull/730), [artifactr ADR-0094](artifactr/adr/0094-diagrams-revisions-thinned-to-one-an-actor-every-ten-minutes.md)). It forgets the named earlier revisions of an artifact, within the scope, and returns how many it forgot. It never forgets the current version, whatever `versions` names, passes over a version it doesn't hold, and leaves the log's events alone. Diagrams' retention, `thin_revisions`, calls it, with at most 500 versions a call. Given the deployment's `integrations`, as stackr's template gives them, it does nothing in a workspace where diagrams are off; called without them, it thins every diagram it finds.

`InMemoryStorage`'s two methods are the shortest complete examples. Run artifactr's workspace behaviour suite, in [`tests/workspace/`](https://github.com/alexnodeland/lattice/tree/main/packages/artifactr/tests/workspace), against your storage: it holds both to their contracts.

## Migrations

Each package migrates its own tables, and a generated application runs every migration as it starts. Nothing needs running by hand, but back the database up first: on a single host, `make backup` in stackr, which needs its `BACKUP_S3_*` settings ([a single host](stackr/guides/single-host.md)); elsewhere, however your database is backed up.

| Package | New migrations | What they add |
|---|---|---|
| artifactr | `files` 0001 and 0002 | Native files' blobs and check-outs, in a schema of their own, kept apart by tenant |
| grantr | 0006 and 0007 | Integrations: each tenant's and workspace's switches; settings, each tenant's and workspace's narrowed limits |
| portalr | analytics 0001 to 0004 | Product analytics' bookkeeping: people's answers to analytics and to session replay, the deletions owed people removed from a tenant, and how far grantr's audit log has been read for them |
| relayr | 0005, 0006, 0007 | Task trackers: the items filed, their followers, and when each was read |
| reflexr, lattice-core, evalr | none | |

Each is additive: no table is dropped or rewritten, and the 0.1 data stays where it was.

## Integrations, switched per workspace

Forms, dashboards, mini apps, native files' apps, task trackers, Excalidraw, Mermaid, math and connected apps are each an integration, switched by a tenant's admin for the tenant and for each workspace ([lattice ADR-0027](adr/0027-integrations-switched-per-workspace-through-one-port.md)).

An upgraded workspace has nothing set, so each integration the deployment installs is at its default:

- **On:** WordCraft, forms, dashboards, math, and Plane and Vikunja.
- **Off:** every other native files' app, mini apps, Excalidraw's diagrams, Mermaid, and the connected apps and their code.

Diagrams, the `excalidraw` integration, are new in 0.2 ([RFC-0006](rfcs/0006-excalidraw-diagrams-drawn-live.md)). Once a workspace switches them on, the agent draws and edits a diagram from Mermaid or shapes, through stackr's diagrams worker (`make up DIAGRAMS=on`), and people edit it on its canvas in portalr, with images on it, each seeing who else has it open and the others' revisions as they arrive. Its older revisions are thinned to one an actor every ten minutes, and its commits reach relayr as the elements they changed, with comments anchored to them. Not built yet: presence across processes (it is passed on within one process, so peers on different replicas don't see each other), commenting from the canvas, agents as peers on it, and Excalidraw's CJK face, Xiaolai, which waits on its author.

An integration the deployment doesn't install is off whatever is set: a native files' app is installed only while `FILES_CRAFTS` names it, and a tracker only with its recipe. lattice-core's `KNOWN` is the list, with each default.

## New settings

A generated application reads these from its `.env`. `copier update` never touches `.env`, so copy what you want from the new `.env.example`. Each one's default leaves the application as it was, but for `PORTAL_SUPABASE_URL`, which an application from 0.1 must change:

| Setting | Default | What it does |
|---|---|---|
| `FILES_CRAFTS` | empty: native files off | The apps whose workers run, such as `wordcraft,gridcraft` ([native files](artifactr/files/guides/native-files.md)) |
| `FILES_<APP>_TOKEN` | none: required for each app `FILES_CRAFTS` names | Each worker's own token, at least 32 characters. `make env` writes them only into a new `.env`; in yours, set each with `openssl rand -hex 32` |
| `FILES_WORKER_MEMORY`, `FILES_WORKER_CPUS`, `FILES_WORKER_TMPFS`, `FILES_WORKER_LIMITS` | 3g, 2, 1g, artifactr's | Each worker's container, and each call's limits |
| `FILES_UPLOADS_PER_MINUTE`, `_AT_ONCE`, `_PER_TENANT`, `_EACH`, `FILES_READINGS` | 20, 8, half, 2, 2 | How people's uploads are held back ([uploads and quotas](artifactr/files/guides/uploads.md)) |
| `FILES_WORKSPACE_QUOTA`, `FILES_TENANT_QUOTA` | none | The most a workspace's or a tenant's files may hold |
| `FILES_EDITORS` | each editor on this machine | Where people's browsers reach each app's editor |
| `PORTAL_BRAND_DIR` | lattice's own look | The deployment's brand kit ([white-labelling](portalr/guides/white-labelling.md)) |
| `PORTAL_SUPABASE_URL` | `/` | `/` signs the portal in on the application's own origin; an application from before 0.2 names Supabase's address here, and should set `/` ([stackr ADR-0042](stackr/adr/0042-a-generated-application-as-a-local-product.md)) |
| `PORTAL_URL`, `PORTAL_APPS_URL` | this machine | The portal's origin, and the mini apps' origin, which only the portal may frame |

In stackr's own `.env`: `STACKR_GATEWAY_MODELS` and `STACKR_UPSTREAM_*` point the gateway's `default` and `fast` at a gateway of your own ([the gateway](stackr/guides/gateway.md)); leave them unset for the providers, as before.

## Local Supabase on Docker 29

`make up` in stackr now checks where Docker publishes on local Supabase's network before it starts Supabase. Some engines, Docker Desktop 29.4 among them, ignore the setting that keeps it on the loopback and publish on every interface, where Supabase's well-known keys and the password `postgres` would be anyone's. On such an engine, `make up` refuses to start local Supabase and says why. There is deliberately no override: set `STACKR_DATABASE=postgres` in `.env` and add the `auth` profile, whose ports are published at `STACKR_BIND` explicitly ([stackr ADR-0045](stackr/adr/0045-local-supabase-only-where-docker-keeps-it-on-the-loopback.md)). `STACKR_BIND=0.0.0.0` with local Supabase is now always refused.

## Updating a generated application

1. Commit everything, so `copier update` can show you its changes.
2. `uvx copier update`, and answer the new questions: `native_files` (yes adds the plumbing; no app runs until `FILES_CRAFTS` names one), and `portal` and `ui` if the application predates them ([the template](stackr/guides/template.md#the-template-copier-update)). It pins lattice's libraries at the template's own commit, so the update moves them too.
3. `uv lock`, then `make check`.
4. Copy the new settings you want from `.env.example` into `.env`. `make env` leaves an existing `.env` alone, so for each app `FILES_CRAFTS` names, set `FILES_<APP>_TOKEN` yourself (`openssl rand -hex 32`): the application won't start without it.
5. `make up`: the image is built again, the migrations run as it starts, and `FILES_CRAFTS`' workers start beside it.
6. Switch on what each tenant and workspace should have, in the admin UI's integrations.
