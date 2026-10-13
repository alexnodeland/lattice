# Architecture

portalr's design is [lattice RFC-0002](../rfcs/0002-portalr-the-portal.md), and its plan [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). Its decisions are in [`adr/`](adr/README.md). This page describes what exists.

## The parts

| Part | Holds |
|---|---|
| `portalr.actions` | portalr's catalog: `portalr:read_telemetry`, `portalr:read_spend` and `portalr:read_deployment`, for `Grants(catalogs=...)` |
| `portalr.tenant` | `Tenant`, read-only, which only `allowed()` makes; the layering test keeps `allowed()` to the router, which calls it after grantr allows the read |
| `portalr.readers` | One reader per tool: `Tempo`, `Loki`, `Prometheus` (through prom-label-proxy), `Langfuse` and `LiteLLM`, and `Grafana` for operators' deep links. `Readers` holds those the stack runs. The only code that talks to the tools |
| `portalr.invites` | `Invite`, and `SupabaseInvite` over Supabase Auth's admin API |
| `portalr.fastapi` | `portalr_router`, its `Site` settings, the UIs' serving, and its OpenAPI document |
| `web/` | The Bun workspace: `client`, `ui`, `app` and `admin` ([ADR-0008](adr/0008-the-bun-workspace-runs-in-bun.md)) |

## The router

An application mounts `portalr_router(resolve_actor=, grants=, readers=, invite=, site=)` at `/portalr` ([ADR-0011](adr/0011-the-router-and-its-readers.md)). `grants` is grantr's `Grants`, with portalr's catalog, `portalr.actions.ACTIONS`, among its catalogs: grantr's roles give a tenant's owners and admins its reads, and operators the deployment's.

| Route | Answers | Needs |
|---|---|---|
| `/portalr/app/`, `/portalr/admin/` | The built UIs: hashed assets cached for good, the index for every client-side route, a strict Content-Security-Policy | Nothing |
| `GET /portalr/config.json` | Supabase's URL and publishable key, the surfaces' paths, and which tools are configured | Nothing |
| `GET /portalr/v1/traces`, `/traces/{id}` | The tenant's traces, a session's or a run's, and one trace's spans, from Tempo | `portalr:read_telemetry` |
| `GET /portalr/v1/logs` | The tenant's logs, a thread's or a run's, from Loki | `portalr:read_telemetry` |
| `GET /portalr/v1/metrics` | `turn_latency`, or `failed_turns` counted over each step, over time, from Prometheus through prom-label-proxy | `portalr:read_telemetry` |
| `GET /portalr/v1/scores` | The tenant's feedback and evaluation scores, newest first, each with its trace's workspace, from Langfuse, and whether they are all there were (ADR-0027) | `portalr:read_telemetry` |
| `GET /portalr/v1/feedback` | The tenant's feedback and evaluations in a window of at most 91 days, or one workspace's, summed by day in UTC from its scores, within the read's bounds ([ADR-0027](adr/0027-feedback-and-evaluations.md)) | `portalr:read_telemetry` |
| `GET /portalr/v1/spend` | The tenant's spend against its budget, from its LiteLLM team | `portalr:read_spend` |
| `GET /portalr/v1/deployment/tenants` | Every tenant, and their spend from one LiteLLM team list | `portalr:read_deployment` |
| `GET /portalr/v1/deployment/links` | Deep links into Langfuse and Grafana | `portalr:read_deployment` |
| `POST /portalr/v1/invites` | Invites someone through Supabase Auth, and adds them to the tenant in grantr | `grantr:add_member` |

Each read names its tenant with `X-Tenant`. Each answers `ok`, `unavailable` or `unconfigured`, so a tool that is down fails only its own read. A refused request answers 400, 401, 403 or 422 with a `Refused` body, as artifactr's and reflexr's routers do. `schemas/portalr.openapi.json` is the routes' document, and a test holds it to the router.

## The readers

Each reader takes a `Tenant` and typed parameters, and builds its query with the tenant first:

| Tool | The tenant, in every query |
|---|---|
| Tempo | `span.tenant.id`, in TraceQL. A trace read by its id is the tenant's only if one span names it and none names another |
| Loki | `tenant_id`, the structured metadata the collector's `tenant.id` becomes |
| Prometheus | `tenant_id` in every selector, and prom-label-proxy's `tenant_id` parameter, which rewrites every selector |
| Langfuse | The traces' `tenant:<id>` tag: Langfuse 4's observations API finds the tenant's traces by it, checked again on each, and only scores on those traces are kept |
| LiteLLM | The tenant's team, `tenant-<id>`, checked again on its answer |

`tests/readers/test_queries.py` builds every query each reader can send, and fails if one lacks its tenant.

## The acceptance tests

`moon run portalr:api` starts a test application, `tests/app/`, beside Tempo, Loki, Prometheus and prom-label-proxy, from `compose.yaml` and stackr's configuration ([ADR-0012](adr/0012-acceptance-against-a-two-tenant-stack.md)). Then:

1. `tests/acceptance/` seeds two tenants' traces, logs and metrics, one trace shared between them, and reads as each, through the readers and raw through prom-label-proxy: neither sees the other's;
2. the Bruno collection's `up/` reads every route, and checks the refusals;
3. Tempo, Loki and the proxy stop, and `down/` finds each read `unavailable`;
4. Schemathesis runs over `schemas/portalr.openapi.json`.

Langfuse and LiteLLM aren't in that stack, so their reads answer `unavailable` there; contract tests cover them, and stackr's Smoke job reads both up through `scripts/smoke_readers.py`.

## The app

`web/app` is the people's UI, at `/portalr/app/`. It reads `config.json` first, signs in through Supabase Auth's client, `@supabase/auth-js`, and asks the server through `client`'s queries, each carrying the current token and the tenant its route names ([ADR-0014](adr/0014-the-apps-shell.md)). Commands go over each library's stream, except a stored rule's, which goes over reflexr's REST, for an answer to every one; and each live event on a workspace's streams makes stale the reads it changed ([ADR-0020](adr/0020-the-rules-area.md)).

| Route | Shows |
|---|---|
| `/sign-in` | An email and a password |
| `/` | The person's tenants, from grantr's `/me`: none is no access, and one goes straight to it |
| `/t/$tenant` | The workspaces grantr says they can open there |
| `/t/$tenant/w/$workspace` | A workspace's threads, and a new one; its artifactr stream is open while any of its routes is |
| `/t/$tenant/w/$workspace/threads/$thread` | A thread's chat: its messages, its runs as they stream, what a paused run waits on, its proposals, and a message to post where grantr allows; and its menu, to restrict and share it ([ADR-0022](adr/0022-restricting-and-sharing-a-thread.md)) |
| `/t/$tenant/w/$workspace/artifacts` | The workspace's artifacts that aren't archived, each by kind and latest version |
| `/t/$tenant/w/$workspace/artifacts/$artifact` | An artifact through its kind's renderer, its revisions newest first with what each changed, and its open proposals |
| `/t/$tenant/w/$workspace/proposals` | Every proposal in the workspace, the open ones first, to accept or reject |
| `/t/$tenant/w/$workspace/runs` | The agent's turns and the rules' runs, newest first, with Stop, Retry, Skip and Cancel as each library and grantr allow, and thumbs on each |
| `/t/$tenant/w/$workspace/rules` | The workspace's rules, each with its origin, version and how far it has read, the schedules that tick into it, and a stored rule installed from its JSON where grantr allows |
| `/t/$tenant/w/$workspace/rules/$rule` | A rule: a code rule's JSON, or a stored rule's, edited and archived where grantr allows |

TanStack Router's route tree, `src/routeTree.gen.ts`, is committed, and a test holds it to `src/routes/`. `moon run app:bdd` runs one feature per area through playwright-bdd, in Bun, against the test application with Supabase Auth (GoTrue, alone) in compose's `bdd` profile, served at `/auth/v1` on its origin ([ADR-0013](adr/0013-the-apps-scenarios-against-the-test-application.md)).

## The chat

`ui`'s chat renders what `client`'s artifactr store holds, and hands each command to its caller ([ADR-0015](adr/0015-the-chat-components-and-streamdown.md)):

| Component | Renders | Sends |
|---|---|---|
| `Messages`, `Message`, `Streaming` | A thread's messages, oldest first, and what a run is streaming | Thumbs on a message |
| `Composer` | A message being written | The message |
| `ToolCall` | A tool a run called, and how it returned | Nothing |
| `Request` | What a paused run waits on: a call to approve, or a question | An approval, a denial or an answer |
| `ProposalCard` | A proposed change, its rationale and how it was resolved | Accept or reject |
| `RunStatus` | How a run is going | Nothing |
| `ArtifactContent`, `rendererFor`, `markdown`, `json` | An artifact, through the renderer its kind is registered with, or as JSON | Nothing |
| `Diff` | What a revision changed, as `client`'s `changes` cut it | Nothing |
| `Thumbs` | The reader's thumbs on a message, an artifact or a run, and why | Thumbs, then a comment ([ADR-0018](adr/0018-the-runs-area-and-feedback.md)) |
| `CommandButton` | One action, waiting while its command is in flight | The command |
| `Markdown` | Markdown through Streamdown: no raw HTML, links to the web, mail, the page and the application alone, images from this origin alone | Nothing |

`ui` imports `client`'s types alone, which a root test holds it to.

## admin

`web/admin` is the UI for a tenant's owners and admins and the deployment's operators, at `/portalr/admin/`, on the app's session ([ADR-0023](adr/0023-admins-shell-and-home.md)). The session, where each UI opens, `allowedIn` and `useMe` are `client`'s; signing in, the account and the tenant switch are `ui`'s.

| Route | Shows |
|---|---|
| `/sign-in` | An email and a password |
| `/` | Where admin opens: its last choice while still the person's, their one tenant, every tenant for an operator, a choice, or no access |
| `/t/$tenant` | A tenant someone owns or administers, in admin's frame, with the areas grantr allows |
| `/t/$tenant/` | Home: members, workspaces, feedback, failed turns and spend, each a card from one read, with its own state |
| `/t/$tenant/access/members`, `/groups`, `/keys`, `/roles`, `/grants` | Access: members, invited or made as service principals, and removed; groups; keys, a secret shown once, and revoked; roles, built in and custom; and grants, given and revoked. Each part where grantr allows its read, as a table or, on a phone, cards ([ADR-0024](adr/0024-access-members-groups-and-keys.md), [ADR-0025](adr/0025-access-roles-and-grants.md)) |
| `/t/$tenant/audit` | Audit: grantr's log for the tenant, the newest on top, a sentence per change with who made it and when, filtered by type and maker in the address ([ADR-0026](adr/0026-audit.md)) |
| `/t/$tenant/feedback` | Feedback: people's thumbs per day, each evaluation's mean per day, each workspace's share and thumbs, and what people said, from portalr's summary, in a window and a workspace the address keeps ([ADR-0027](adr/0027-feedback-and-evaluations.md)) |
| `/deployment` | Every tenant, for operators, with the deployment's areas alone |
| `/deployment/` | Home: the tenants, and their spend |

`moon run admin:bdd` runs admin's features against the test application, which sends its telemetry through stackr's Collector to Tempo, Loki and Prometheus, with Langfuse and LiteLLM unconfigured.

## The kit's look

`ui`'s tokens are lattice ADR-0014's, with `--edge`, `--wash`, `--accent-hover` and `--scrim` beside them ([ADR-0019](adr/0019-the-kits-look.md)), and `--danger`, for destructive actions alone ([ADR-0021](adr/0021-the-areas-on-the-frame-and-what-admin-needs.md)), each pair's contrast asserted in both schemes. Its typefaces, Schibsted Grotesk and Fragment Mono, are served from the UIs' own origin. The frame and its parts:

| Component | What it is |
|---|---|
| `AppShell` | The frame: a rail from 1024 pixels, a bar and a drawer below, and the mark of `app` or `admin` |
| `SideNav`, `NavLink` | The areas, the current one marked, with how many wait for the reader |
| `Switcher` | The tenant and the workspace, and a menu of the others |
| `AccountMenu` | Who is signed in, their scheme, and signing out |
| `PageHeader` | A page's way back, its one heading, a line about it, and its actions |
| `Card`, `EmptyState`, `Table` | What asks something of the reader; nothing yet, and what to do; rows, named by a caption or by a heading beside them, a row's header in the row's own type |
| `Rows`, `Row`, `RowLink`, `SectionTitle` | A lined list, each row's link stretched over it; a section's heading |
| `Plain` | A page outside the frame: the lockup as a link home, the account if signed in, and one column |
| `StatusBadge` | How a thing is going, as a shape and a word; only waiting for you in the working colour; a budget near or over as a word and a shape of its own, with no warning colour |
| `ConfirmDialog` | A destructive action, asked first: what will be lost, the focus on Cancel, and a name to type where asked; its trigger named in full where its words are short |
| `SegmentedFilter` | One filter of a few, side by side |
| `TenantSwitcher` | admin's tenant, or every tenant, and a menu of the others |
| `StatCard` | One figure, read on its own, or why there's none |
| `ItemTable` | Items as a table from 640 pixels, each row named by its first cell or a name of its own, and as headed cards below, one in the accessibility tree; an `EmptyState` with none |
| `TabNav`, `TabLink` | An area's parts as tabs of links, the current one marked with `aria-current` |
| `CheckboxGroup` | Several choices, any of them checked, named by a legend |
| `SignIn`, `Account` | Signing in, and the account menu over a session, for both UIs |
| `BarChart`, `LineChart`, `DonutChart` | Tremor's charts, adapted, on Recharts: the inks as marks, a pattern and a label per series, and the figures as a table ([ADR-0027](adr/0027-feedback-and-evaluations.md)) |
| `Moment` | A time in the reader's zone, and how long ago on hover ([ADR-0026](adr/0026-audit.md)) |
| `Dialog` | A dialog over the page, opened by its caller, with where focus starts and where it returns ([ADR-0022](adr/0022-restricting-and-sharing-a-thread.md)) |
| `Menu` | A button and the actions it opens, each of which may be disabled while it's being done |
| `SelectField` | A labelled choice among a few, as the platform's own select, which submits with its form |
| `Icon`, `Mark`, `Lockup` | A Lucide icon beside its word; portalr's marks |

`gallery.screenshot.test.tsx` pins how they sit together, wide and narrow, in each scheme. It runs in CI alone, against Linux baselines.

Every area of a workspace renders in `AppShell`. The screens outside one are ui's `Plain` page: choosing a tenant or a workspace, with the account, and what went wrong, without it. Signing in is a card of its own. `admin` renders its frame, with its own mark.

## The wheel

Vite builds `app` and `admin` into `src/portalr/static/`, which git ignores and the wheel carries. portalr's `build` depends on theirs, and `ui-in-wheel`, in `check` and the release workflow, fails unless this version's wheel holds both, each with its typefaces, and the typefaces' licences.
