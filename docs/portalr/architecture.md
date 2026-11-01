# Architecture

portalr's design is [lattice RFC-0002](../rfcs/0002-portalr-the-portal.md), and its plan [RFC-0001](rfcs/0001-v0.1-implementation-plan.md). Its decisions are in [`adr/`](adr/README.md). This page describes what exists.

## The parts

| Part | Holds |
|---|---|
| `portalr.actions` | portalr's catalog: `portalr:read_telemetry`, `portalr:read_spend` and `portalr:read_deployment`, for `Grants(catalogs=...)` |
| `portalr.tenant` | `Tenant`, read-only, which only `allowed()` makes; the layering test keeps `allowed()` to the router, which calls it after grantr allows the read |
| `portalr.readers` | One reader per tool: `Tempo`, `Loki`, `Prometheus` (through prom-label-proxy), `Langfuse` and `LiteLLM`, and `Grafana` for operators' deep links. `Readers` holds those the stack runs. The only code that talks to the tools |
| `portalr.commands` | portalr's commands for lattice-core: its admin's reads, creating a tenant and inviting a member, each a `command` capability in the `admin` toolset, a read taking its route's query, and its document `schemas/portalr.commands.json` ([ADR-0094](adr/0094-portalrs-commands-its-admins-reads-and-the-tenant-and-member-it-makes.md)). It reads no tool |
| `portalr.invites` | `Invite`, and `SupabaseInvite` over Supabase Auth's admin API |
| `portalr.people` | `People`, the hook that names people by email, and `SupabasePeople` over Supabase Auth's admin API, with a short in-memory cache ([ADR-0038](adr/0038-people-by-email.md)) |
| `portalr.fastapi` | `portalr_router`, its `Site` settings, the UIs' serving, and its OpenAPI document |
| `web/` | The Bun workspace: `client`, `ui`, `app` and `admin` ([ADR-0008](adr/0008-the-bun-workspace-runs-in-bun.md)) |

## The router

An application mounts `portalr_router(resolve_actor=, grants=, readers=, invite=, site=, people=)` at `/portalr` ([ADR-0011](adr/0011-the-router-and-its-readers.md)). `grants` is grantr's `Grants`, with portalr's catalog, `portalr.actions.ACTIONS`, among its catalogs: grantr's roles give a tenant's owners and admins its reads, and operators the deployment's.

Each route under `/portalr` says in the document's `x-lattice-command` the command it calls, or why it calls none: `config.json`, a person's own analytics consent and session, the analytics relay, people's emails and the models a turn may use are no commands. lattice's parity test holds them to the catalogs (lattice [ADR-0042](../adr/0042-parity-every-operation-names-its-command-and-one-test-holds-the-catalogs-to-grantr.md)).

| Route | Answers | Needs |
|---|---|---|
| `/portalr/app/`, `/portalr/admin/` | The built UIs: hashed assets cached for good, the index for every client-side route, a strict Content-Security-Policy | Nothing |
| `GET /portalr/config.json` | Supabase's URL and publishable key, the surfaces' paths, which tools are configured, whether people are named, each native file's app's hosted editor ([ADR-0049](adr/0049-checking-a-native-file-out-and-in.md)), and the origin mini apps run on ([ADR-0051](adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) | Nothing |
| `GET /` on the apps' origin | Mini apps' sandbox, served by `SandboxOrigin` to requests for that origin alone, under its own policy; anything else asked of it is not found ([ADR-0051](adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) | Nothing |
| `GET /portalr/v1/traces`, `/traces/{id}` | The tenant's traces, a session's or a run's, and one trace's spans, each once, with only the attributes known to be safe: the rest are named, and given for one span with `content=true&span=`, not kept ([ADR-0030](adr/0030-traces-and-the-trace-view.md)) | `portalr:read_telemetry` |
| `GET /portalr/v1/logs`, `/logs/{record_id}` | The tenant's newest logs in a window of at most 24 hours, a thread's or a run's, without their lines and with only the labels known to be safe; one record's line, `no-store`, when asked for ([ADR-0031](adr/0031-logs-and-health.md)) | `portalr:read_telemetry` |
| `GET /portalr/v1/metrics` | `turn_latency`, or `failed_turns` counted over each step, over time, from Prometheus through prom-label-proxy | `portalr:read_telemetry` |
| `GET /portalr/v1/scores` | The tenant's feedback and evaluation scores, newest first, each with its trace's workspace, from Langfuse, and whether they are all there were (ADR-0027) | `portalr:read_telemetry` |
| `GET /portalr/v1/feedback` | The tenant's feedback and evaluations in a window of at most 91 days, or one workspace's, summed by day in UTC from its scores, within the read's bounds ([ADR-0027](adr/0027-feedback-and-evaluations.md)) | `portalr:read_telemetry` |
| `GET /portalr/v1/spend` | The tenant's spend against its budget, from its LiteLLM team | `portalr:read_spend` |
| `GET /portalr/v1/usage` | The tenant's spend per day in a window of at most 91 days, from its LiteLLM team, each named workspace's from its `tenant-workspace:` tag, and a day's share of its budget, within the read's bounds ([ADR-0028](adr/0028-usage-and-spend.md)) | `portalr:read_spend` |
| `GET /portalr/v1/deployment/tenants` | Every tenant, and their spend from one LiteLLM team list | `portalr:read_deployment` |
| `POST /portalr/v1/deployment/tenants` | Creates a tenant, its first owner invited or found by email through Supabase Auth, then made by grantr; the tenant and the owner's user id are answered, never the email ([ADR-0034](adr/0034-tenants-and-the-deployments-audit.md)) | `portalr:read_deployment`, and `grantr:create_tenant` |
| `GET /portalr/v1/deployment/links` | Deep links into Langfuse and Grafana for a trace, a session, a run or a tenant, each recorded on `portalr.access` with who and the kinds of id, never an id's content ([ADR-0035](adr/0035-tools-and-the-record-of-opening-them.md)) | `portalr:read_deployment` |
| `GET /portalr/v1/people` | The emails of up to 100 people by user id: a tenant's members see its other members', an operator anyone's, with or without a tenant; an id not allowed, unknown or without an email is left out, alike, and Supabase is asked only about the ids allowed. `no-store` ([ADR-0038](adr/0038-people-by-email.md)) | Membership of `X-Tenant`, or `portalr:read_deployment` |
| `POST /portalr/v1/invites` | Invites someone through Supabase Auth, and adds them to the tenant in grantr | `grantr:add_member` |

Each read names its tenant with `X-Tenant`. Each answers `ok`, `unavailable` or `unconfigured`, so a tool that is down fails only its own read. A refused request answers 400, 401, 403 or 422 with a `Refused` body, as artifactr's and reflexr's routers do: lattice-core's, from which `refusals` builds the four statuses it documents ([lattice ADR-0021](../adr/0021-the-refusal-schema-needs-no-extra.md)). `schemas/portalr.openapi.json` is the routes' document, and a test holds it to the router.

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

`web/client` holds the types `client:types` generates from the packages' committed documents ([ADR-0010](adr/0010-the-client-generated-types-and-resumable-stores.md)): each surface's OpenAPI document, each stream's JSON Schema, lattice's integrations, and `CommandName`, the union of every command the libraries' catalogs declare, with `COMMANDS`, their names as a constant, so a name that is no command fails `tsc` ([lattice RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)). A drift test holds each to its document.

Every request the client sends names its command first, as its operation's `x-lattice-command` says: `client:types` writes `Calls`, what each operation calls, and `Api`'s clients take the command before the path, so a request that names another, or none where its operation calls one, fails `tsc`. An operation that calls none takes `null`, and one whose body carries command frames `"frames"`. `commands.used.json`, beside `client`'s `src`, lists every command the UIs' requests name; `client:types` writes it from their sources, a drift test holds it to them, and lattice's parity test fails on one that no catalog declares or portalr doesn't offer ([ADR-0096](adr/0096-every-request-portalrs-client-sends-names-its-command.md)).

`web/app` is the people's UI, at `/portalr/app/`. It reads `config.json` first, signs in through Supabase Auth's client, `@supabase/auth-js`, and asks the server through `client`'s queries, each carrying the current token and the tenant its route names ([ADR-0014](adr/0014-the-apps-shell.md)). Commands go over each library's stream, except a stored rule's, which goes over reflexr's REST, for an answer to every one; and each live event on a workspace's streams makes stale the reads it changed ([ADR-0020](adr/0020-the-rules-area.md)). What a workspace's runs filed in its tracker is read from relayr's own route, where `config.json`'s `surfaces.relayr` names one, and its runs' chains and the `tracker:` events that fired them come from reflexr's stream ([ADR-0047](adr/0046-tracker-links-on-runs.md)). A workspace's integrations are read once as it opens, from grantr, and kept: they say which of Markdown's add-ons it may draw, each is its registry default where they can't be read, and a command artifactr refuses as `not_enabled` reads them again ([ADR-0045](adr/0045-integrations-in-admin-and-the-apps-read-of-them.md)).

| Route | Shows |
|---|---|
| `/sign-in` | An email and a password |
| `/` | The person's tenants, from grantr's `/me`: none is no access, and one goes straight to it |
| `/t/$tenant` | The workspaces grantr says they can open there |
| `/t/$tenant/$` | A page that isn't there under a tenant: "Page not found", on a plain page ([ADR-0068](adr/0068-where-the-focus-goes-and-one-not-found.md)) |
| `/t/$tenant/approvals` | The approvals waiting in the tenant that grantr says the reader may answer, oldest first, from every workspace, each opening its page, or a confirmation admin's confirm page ([ADR-0093](adr/0093-approvals-on-their-own-page-and-a-confirmation-on-admins-confirm-page-alone.md)) |
| `/t/$tenant/approvals/$approval` | An approval as it stands, for one who may answer it or the person it was asked for: what the call would do, who asked, who may answer it while it waits ([ADR-0095](adr/0095-a-threads-approval-card-links-its-approvals-page-which-says-who-may-answer-it.md)) and where it stands; approved or denied there, on `portalr`, by one who may, with a reason; a confirmation linked to admin's confirm page ([ADR-0093](adr/0093-approvals-on-their-own-page-and-a-confirmation-on-admins-confirm-page-alone.md)) |
| `/t/$tenant/w/$workspace` | A workspace's threads, and a new one; its artifactr stream is open while any of its routes is, and its integrations are read as it opens |
| `/t/$tenant/w/$workspace/threads/$thread` | A thread's chat: its messages, and among them the artifacts made in it, each kind the app draws: a mini app running ([ADR-0052](adr/0052-artifacts-inline-in-their-thread.md)), a form sent from there, and a native file read a page at a time, or its cells, and checked out or edited in its framed editor ([ADR-0055](adr/0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md)), its runs as they stream, what a paused run waits on, its proposals, and a message to post where grantr allows; and its menu, to restrict and share it ([ADR-0022](adr/0022-restricting-and-sharing-a-thread.md)) |
| `/t/$tenant/w/$workspace/artifacts` | The workspace's artifacts that aren't archived, each by kind and latest version |
| `/t/$tenant/w/$workspace/artifacts/$artifact` | An artifact through its kind's renderer, its revisions newest first with what each changed, and its open proposals; for a native file, who has it, its pages, a download, and each revision's words compared on demand ([ADR-0048](adr/0048-native-files-in-the-app.md)), checking it out, which opens its app's hosted editor on an origin of its own, and in, with the upload's progress ([ADR-0049](adr/0049-checking-a-native-file-out-and-in.md)), and its open proposals as on the workspace's proposals ([ADR-0050](adr/0050-a-native-files-proposals-and-the-pilots-scenarios.md)); and for a mini app, the app running in its sandbox, with the integrations read again every half minute while it does ([ADR-0051](adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) |
| `/t/$tenant/w/$workspace/proposals` | Every proposal in the workspace, the open ones first, to accept or reject; a native file's with how it was made, whether it is outdated, and its words and pages beside the head's ([ADR-0050](adr/0050-a-native-files-proposals-and-the-pilots-scenarios.md)) |
| `/t/$tenant/w/$workspace/runs` | The agent's turns and the rules' runs, newest first, with Stop, Retry, Skip and Cancel as each library and grantr allow, and thumbs on each; a rule's run links to the tracker items its chain filed, from relayr's read, and to those whose `tracker:` events set it off ([ADR-0046](adr/0046-tracker-links-on-runs.md)) |
| `/t/$tenant/w/$workspace/rules` | The workspace's rules, each with its origin, version and how far it has read, the schedules that tick into it, and a stored rule installed from its JSON where grantr allows |
| `/t/$tenant/w/$workspace/rules/$rule` | A rule: a code rule's JSON, or a stored rule's, edited and archived where grantr allows |
| `/t/$tenant/w/$workspace/$` | A page that isn't there in a workspace: "Page not found", in its frame ([ADR-0068](adr/0068-where-the-focus-goes-and-one-not-found.md)) |

TanStack Router's route tree, `src/routeTree.gen.ts`, is committed, and a test holds it to `src/routes/`. `moon run app:bdd` runs one feature per area through playwright-bdd, in Bun, against the test application with Supabase Auth (GoTrue, alone) in compose's `bdd` profile, served at `/auth/v1` on its origin ([ADR-0013](adr/0013-the-apps-scenarios-against-the-test-application.md)). The native files' scenarios check files out to the hosted editor, a stand-in for WordCraft's build that compose's `editor` profile serves on a port of its own, which the script starts first and names to the application ([ADR-0050](adr/0050-a-native-files-proposals-and-the-pilots-scenarios.md)).

## The chat

`ui`'s chat renders what `client`'s artifactr store holds, and hands each command to its caller ([ADR-0015](adr/0015-the-chat-components-and-streamdown.md)):

| Component | Renders | Sends |
|---|---|---|
| `Messages`, `Message`, `Streaming` | A thread's messages, oldest first, the reader's at the end of the line and everyone else's at its start, a message on its way, and what a run is streaming: its thinking, folded, then its words, never announced as they grow ([ADR-0053](adr/0053-the-chats-questions-tool-calls-sides-failures-and-streaming.md), [ADR-0083](adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md)); what a failed or stopped turn had streamed, quietly | Thumbs on a message; a message copied as the Markdown it was written in ([ADR-0043](adr/0043-markdowns-basics.md)) |
| `Composer` | A message being written, cleared as it is sent and put back if it isn't | The message |
| `ToolCalls`, `ToolCall` | A run's calls, each a summary of its name, status and arguments, or why it failed, that opens to its arguments and result, each formatted, with a string's lines or code as a block of its own, or raw, as the `json-view` add-on draws them once a call is opened ([ADR-0083](adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md)) | Nothing |
| `Questions` | What the agent asks through `ask_user`: radio and checkbox groups, recommended options first, words of the reader's own where offered; once answered, what was chosen and by whom | Each question's answer |
| `RunFailed` | A failed turn: why, and the run's own error | "Try again", on the thread's latest |
| `Request` | What a paused run waits on: a call to approve, questions, or another tool's question; a call lattice's enforcer deferred links its approval's page, "Who may answer it" ([ADR-0095](adr/0095-a-threads-approval-card-links-its-approvals-page-which-says-who-may-answer-it.md)) | An approval, a denial or an answer |
| `ProposalCard` | A proposed change, its rationale and how it was resolved, and why it can't be accepted where its caller says so | Accept or reject |
| `RunStatus` | How a run is going | Nothing |
| `RunStrip` | The strip over a turn under way: its status, what it is doing and for how long, how long since its last frame once that is a while, and its tokens, estimated until a run says them exactly, with the phase's wording and the token line in the `streaming` add-on ([ADR-0083](adr/0083-a-turn-shows-its-progress-phase-thinking-and-an-estimated-count.md)) | Stop; the way to its question |
| `ArtifactContent`, `rendererFor`, `markdown`, `json` | An artifact, through the renderer its kind is registered with, or as JSON; a renderer also gives its title ([ADR-0029](adr/0029-ui-polish-from-the-screenshots.md)) | Nothing |
| `SchemaForm` | A form an agent wrote as data, in lattice RFC-0005's JSON Schema subset, with the kit's controls; what it or the server refuses is said under each field | The values |
| `DashboardView`, `PANELS` | A dashboard's snapshot: figures, the charts, a table, Markdown and forms by id, each panel drawn by the renderer `panels` registers for its `type` | Nothing of its own |
| `UI_RENDERERS`, `FormHost` | The renderers of artifactr.ui's `form`, `submission`, `dashboard` and `app`; a form sends through the page's `FormHost`, and without one shows its fields, read-only; an app shows its label and summary, and runs nothing | A submission |
| `Diff` | What a revision changed, as `client`'s `changes` cut it | Nothing |
| `nativeFile`, `FileHolder`, `PageStrip`, `PageCompare` | A native file's manifest, its name, type, size, pages and outline; who has it, as a shape and words; its pages, as its app draws them ([ADR-0048](adr/0048-native-files-in-the-app.md)); and two versions' pages side by side, each said changed or not ([ADR-0050](adr/0050-a-native-files-proposals-and-the-pilots-scenarios.md)) | Nothing |
| `FileChooser`, `Progress` | A file to choose through its labelled input, or drop instead; how far an upload has gone ([ADR-0049](adr/0049-checking-a-native-file-out-and-in.md)) | Nothing |
| `AppHostContext` | A mini app, labelled as the agent's, with its summary, run through the page's `AppHost` in the sandbox on the apps' origin, its bridge in the `apps` add-on on MCP Apps' methods; or its label and summary alone where it is archived, mini apps are off or no apps' origin is named ([ADR-0051](adr/0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) | Nothing |
| `InlineArtifact` | An artifact in the thread it was made in, through its kind's renderer, with a link to its page ([ADR-0052](adr/0052-artifacts-inline-in-their-thread.md)); given its kind, named by it, with a full view ([ADR-0055](adr/0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md)) | Nothing |
| `PageViewer`, `SheetTable` | A native file's page at a time, paged by buttons and keys; a workbook's sheet as its cells ([ADR-0055](adr/0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md)) | Nothing |
| `NewVersion`, `NewVersionOffer` | A new build offered to a tab that outlived it: its page's entry script read again every five minutes and on its return, and "Reload" or "Not now" for that build ([ADR-0058](adr/0058-a-new-version-offered-to-a-stale-tab.md)) | Nothing; a reload the person chooses |
| `Disclosure` | A part that opens and closes: a button that says whether it is open and what it opens, in a quiet, link or block look ([ADR-0063](adr/0063-disclosures.md)) | Nothing |
| `Heading`, `Badge` | A heading below the page's, at the outline's level in a look of the type scale; a word in a pill that says what something is ([ADR-0062](adr/0062-badges-and-headings.md)) | Nothing |
| `Thumbs` | The reader's thumbs on a message, an artifact or a run, and why | Thumbs, then a comment ([ADR-0018](adr/0018-the-runs-area-and-feedback.md)) |
| `CommandButton` | One action, waiting while its command is in flight | The command |
| `Markdown` | Markdown through Streamdown: no raw HTML, links to the web, mail, the page and the application alone, images from this origin alone; GitHub's callouts as alerts, footnotes of each message's own, and code blocks with their language, Wrap and Copy ([ADR-0043](adr/0043-markdowns-basics.md)); highlighting in fifteen languages, and math as MathML, each loaded when a message needs it ([ADR-0044](adr/0044-highlighting-and-math-on-demand.md)) | Nothing |
| `IntegrationsContext` | Whether each of lattice's integrations is on, by its key, which the app gives from a workspace's integrations: Markdown's add-ons, where one that isn't drawn shows its source with a quiet line, and whether a form may be sent and a dashboard's charts drawn. Each is its registry default where no page says: all on but Mermaid, which is parked, and mini apps ([ADR-0042](adr/0042-mermaid-cant-draw-under-the-policy.md), [ADR-0045](adr/0045-integrations-in-admin-and-the-apps-read-of-them.md), [ADR-0047](adr/0047-dashboards-on-demand-tables-and-the-panel-registry.md)) | Nothing |

`ui` imports `client`'s types alone, which a root test holds it to. `Markdown` and a dashboard are held to the UIs' Content-Security-Policy too: `ui`'s `csp` tests build a page of them as the UIs are built, serve it with the policy a portalr test holds to the router's, draw each from the page's own task, and fail on any violation in Chromium ([ADR-0043](adr/0043-markdowns-basics.md), [ADR-0047](adr/0047-dashboards-on-demand-tables-and-the-panel-registry.md)).

A dashboard's panels are plain JSON, with nothing in them that runs, and each is drawn by a registry of renderers keyed by its `type`, `PANELS` by default: `StatCard`, `Markdown`, and the `dashboards` add-on, loaded on demand while `ui:dashboards` is on, which holds the kit's charts and a table panel's sorting, filtering and pages on TanStack Table. Another drawing of charts or tables replaces a renderer there, and neither the panels' format nor the artifact's schema changes; each chart's figures are built from its panel, whatever draws it, and are open where the add-on is off or won't load ([ADR-0047](adr/0047-dashboards-on-demand-tables-and-the-panel-registry.md)).

Forms, dashboards and mini apps are switched on and off per workspace by an integration's key, `ui:forms`, `ui:dashboards` and `ui:mini-apps`, as Markdown's add-ons are by `markdown:math` and `markdown:mermaid`, which every part asks through one seam, `IntegrationsContext`, an `isEnabled(key)` over the registry's keys. The app gives it a workspace's integrations through `client`'s `useEnabled`, so each is its registry default until they are read and where they can't be; a page with no read, as admin, has the same defaults, which `ui` writes once and a test holds to the registry ([ADR-0045](adr/0045-integrations-in-admin-and-the-apps-read-of-them.md), [ADR-0047](adr/0047-dashboards-on-demand-tables-and-the-panel-registry.md)). A key that is off degrades to read-only, said as "Not available in this workspace": a form keeps its fields, disabled, says which is off, and has no button; a dashboard still shows its snapshot, and its forms can't be sent; an app is its label and summary, as always in phase 1. With dashboards off, a chart isn't drawn and its figures are open. A command the server refuses as `not_enabled`, which names the integration, degrades the same way, at once, and makes the app read the workspace's integrations again; once that read says the integration is on, the form can be sent again.

## admin

`web/admin` is the UI for a tenant's owners and admins and the deployment's operators, at `/portalr/admin/`, on the app's session ([ADR-0023](adr/0023-admins-shell-and-home.md)). The session, where each UI opens, `allowedIn` and `useMe` are `client`'s; signing in, the account and the tenant switch are `ui`'s.

| Route | Shows |
|---|---|
| `/sign-in` | An email and a password |
| `/` | Where admin opens: its last choice while still the person's, their one tenant, every tenant for an operator, a choice, or no access |
| `/t/$tenant` | A tenant someone owns or administers, in admin's frame, with the areas grantr allows |
| `/t/$tenant/$` | A page that isn't there in a tenant they administer: "Page not found", in the frame ([ADR-0068](adr/0068-where-the-focus-goes-and-one-not-found.md)) |
| `/t/$tenant/` | Home: members, workspaces, feedback, failed turns and spend, each a card from one read, with its own state |
| `/t/$tenant/access/members`, `/groups`, `/keys`, `/roles`, `/grants` | Access: members, invited or made as service principals, and removed; groups; keys, a secret shown once, and revoked; roles, built in and custom; and grants, given and revoked. Each part where grantr allows its read, as a table or, on a phone, cards ([ADR-0024](adr/0024-access-members-groups-and-keys.md), [ADR-0025](adr/0025-access-roles-and-grants.md)) |
| `/t/$tenant/integrations` | Integrations: on the tenant or in a workspace the address chooses, each integration switched on or off, or back to what it inherits, with where its state comes from, the tenant's off and the deployment's not installing as ceilings, and who set it there and when ([ADR-0045](adr/0045-integrations-in-admin-and-the-apps-read-of-them.md)) |
| `/t/$tenant/settings` | Settings: on the tenant or in a workspace the address chooses, each setting lowered, never raised (a superset's names only added to, lattice ADR-0038), or unset, at the version read, with what applies, its ceiling and which layer sets it, what is set here and by whom, and whether it is clamped ([ADR-0067](adr/0067-settings-in-admin.md)) |
| `/t/$tenant/audit` | Audit: grantr's log for the tenant, the newest on top, a sentence per change with who made it and when, filtered by type and maker in the address ([ADR-0026](adr/0026-audit.md)) |
| `/t/$tenant/feedback` | Feedback: people's thumbs per day, each evaluation's mean per day, each workspace's share and thumbs, and what people said, from portalr's summary, in a window and a workspace the address keeps ([ADR-0027](adr/0027-feedback-and-evaluations.md)) |
| `/t/$tenant/traces`, `/traces/$trace` | Traces: the tenant's newest traces in a window, or a thread's or a run's, and a trace's spans as a tree and a waterfall, with what a span withheld read for that span when asked, from Tempo ([ADR-0030](adr/0030-traces-and-the-trace-view.md)) |
| `/t/$tenant/logs` | Logs: the newest records in a window, or a thread's or a run's, with a line read for one record when asked, and Health: a turn's latency and failed turns over time, at a step it says ([ADR-0031](adr/0031-logs-and-health.md)) |
| `/t/$tenant/runs` | Runs: a workspace's rule runs live from reflexr's stream, those needing attention or every one, each retried, skipped or cancelled after a confirmation, once, with what people did to it, and the tracker items its chain filed; beyond the RFC's read-only row ([ADR-0032](adr/0032-runs-in-admin.md), [ADR-0047](adr/0046-tracker-links-on-runs.md)) |
| `/t/$tenant/adoption` | Adoption: people active over the window, its last 7 days and its last 30, and each day; each integration's use; the funnel from a page to a thread to a message; and weekly retention, from portalr's adoption read, in a window the address keeps ([ADR-0071](adr/0071-adoption-the-tenants-read-and-page.md)) |
| `/t/$tenant/usage` | Usage: the spend per day, each day against its share of the budget where there is one, and each workspace's part, from portalr's usage read, in a window the address keeps ([ADR-0028](adr/0028-usage-and-spend.md)) |
| `/confirm/$approval` | The confirm page: the caller's own `admin_high` call, found in whichever of their tenants shows it and read afresh, confirmed on `portalr:confirm` once they type the tenant's name, or cancelled ([ADR-0093](adr/0093-approvals-on-their-own-page-and-a-confirmation-on-admins-confirm-page-alone.md)) |
| `/deployment` | Every tenant, for operators, with the deployment's areas alone |
| `/deployment/` | Home: the tenants, and their spend |
| `/deployment/tenants` | Tenants: every tenant with its spend and budget, fifty at a time, and a tenant created with its owner by email, once confirmed ([ADR-0034](adr/0034-tenants-and-the-deployments-audit.md)) |
| `/deployment/audit` | The deployment's audit log: operators made and revoked, and which tenant each operator created and for whom, newest first ([ADR-0034](adr/0034-tenants-and-the-deployments-audit.md)) |
| `/deployment/tools` | Tools: links into Langfuse and Grafana for the ids given, a notice that they are outside the gates of Traces and Logs, and only web addresses as links ([ADR-0035](adr/0035-tools-and-the-record-of-opening-them.md)) |

`moon run admin:bdd` runs admin's features against the test application, which sends its telemetry through stackr's Collector to Tempo, Loki and Prometheus, with Langfuse and LiteLLM unconfigured.

## The kit's look

`ui`'s tokens are lattice ADR-0014's, with `--edge`, `--wash`, `--accent-hover` and `--scrim` beside them ([ADR-0019](adr/0019-the-kits-look.md)), and `--danger`, for destructive actions alone ([ADR-0021](adr/0021-the-areas-on-the-frame-and-what-admin-needs.md)), each pair's contrast asserted in both schemes. Its typefaces, Schibsted Grotesk and Fragment Mono, are served from the UIs' own origin. The frame and its parts:

| Component | What it is |
|---|---|
| `AppShell` | The app's frame: one bar along the top, with the areas on it from 1024 pixels and as the page's first row below, the search and what waits in its corner; on a phone the areas and the magnifier are a tab bar along the foot (`tabs`) (ADR-0087) |
| `RailShell` | admin's frame: a rail from 1024 pixels, a bar and a drawer below; its classes are `rail.css`'s |
| `PaletteFrame` | A palette's dialog near the top of the window, for the app's search, or, docked, along its foot in a phone's tab bar's place |
| `SideNav`, `NavLink` | admin's areas on its rail, the current one marked, with how many wait for the reader |
| `Switcher` | The tenant and the workspace, or the tenant alone, and a menu of the others |
| `AccountMenu` | Who is signed in, their scheme, and signing out |
| `PageHeader` | A page's way back, its one heading, a line about it, and its actions, set in the kit's type scale (`type.ts`: weights stop at 600), under a page width that centres a wide screen's content |
| `Card`, `EmptyState`, `Table` | What asks something of the reader; nothing yet, and what to do; rows, named by a caption or by a heading beside them, a row's header in the row's own type |
| `Rows`, `Row`, `RowLink`, `SectionTitle` | A lined list, each row's link stretched over it; a section's heading |
| `Plain` | A page outside the frame: the lockup as a link home, the account if signed in, and one column |
| `StatusBadge` | How a thing is going, as a shape and a word, the word in the ink: what failed and a budget over edged and marked in the rose red, what is retrying and a budget near in the gold, succeeded neutral; only waiting for you in the working colour ([ADR-0039](adr/0039-elevation-status-colour-states-and-density.md)) |
| `Alert`, `Reading`, `Skeleton` | A note, a warning or an error in the page, with a shape beside its words and the announcement its tone calls for; what is being read as a status over placeholders in its shape |
| `ConfirmDialog` | A destructive action, asked first: what will be lost, the focus on its way out (Cancel, or words of its own such as "Keep running"), and a name to type where asked; its trigger shows its words alone in a row and is named in full aloud ([ADR-0037](adr/0037-form-controls-and-row-actions.md)) |
| `SegmentedFilter` | One filter of a few, such as a window, side by side, with its label and hint written above and under it when asked, and a `name` to submit with its form |
| `TenantSwitcher` | admin's tenant, or every tenant, and a menu of the others |
| `StatCard` | One figure, read on its own, or why there's none |
| `ItemTable` | Items as a table from 640 pixels, each row named by its first cell or a name of its own, and as headed cards below, one in the accessibility tree; an `EmptyState` with none |
| `TabNav`, `TabLink` | An area's parts as tabs of links, the current one marked with `aria-current`, on one row that scrolls on a phone |
| `CheckboxGroup` | Several choices, any of them checked, named by a legend |
| `SignIn`, `Account` | Signing in, and the account menu over a session, for both UIs |
| `BarChart`, `LineChart`, `DonutChart`, `Tracker` | Tremor's charts, adapted, on Recharts, over one chart theme (`chart-theme.tsx`): violet-led series as marks, patterns only where marks touch, a legend and a tooltip on the menus' surface, and the figures as a table; `data-cvd` on the root switches to a colour-blind palette with every pattern on ([ADR-0027](adr/0027-feedback-and-evaluations.md), [ADR-0036](adr/0036-the-chart-theme-and-colour-blind-mode.md)) |
| `Num` | A figure with tabular digits only, so its decimal point keeps its width ([ADR-0036](adr/0036-the-chart-theme-and-colour-blind-mode.md)) |
| `TraceView` | A trace's spans as an ARIA tree with a waterfall, virtualized, and the chosen span's details; what a span withheld is shown when asked for ([ADR-0030](adr/0030-traces-and-the-trace-view.md)) |
| `LogList`, `AnsiText` | Log records as a virtualized ARIA listbox with the chosen record's details; a line in the eight palette colours and bold, with every other escape stripped ([ADR-0031](adr/0031-logs-and-health.md)) |
| `IntegrationList` | A level's integrations as a table, or cards on a phone: each a switch named by it and described by its state in words, a badge whose shape says on or off, where the state comes from, who set it and when, and a way back to what it inherits; a ceiling's switch disabled with its reason ([ADR-0045](adr/0045-integrations-in-admin-and-the-apps-read-of-them.md)) |
| `RunList`, `RuleRunStatus` | Rule runs as a table, or cards on a phone, with each row's actions, and a run's status as a word and a shape ([ADR-0032](adr/0032-runs-in-admin.md)) |
| `Tracker` | Tremor's tracker, adapted: a block per day, each in its level's mark, a pattern past the second, the levels in a legend, and the figures as a table ([ADR-0028](adr/0028-usage-and-spend.md)) |
| `Moment` | A time in the reader's zone, and how long ago on hover ([ADR-0026](adr/0026-audit.md)) |
| `TrackerItems`, `safeHref` | Items in a task tracker after a label, such as "Filed as": each a link that opens it in a new tab, named with its tracker, a deleted one struck through and said so; only an http or https address is ever a link ([ADR-0047](adr/0046-tracker-links-on-runs.md)) |
| `Dialog` | A dialog over the page, opened by its caller, with where focus starts and where it returns ([ADR-0022](adr/0022-restricting-and-sharing-a-thread.md)) |
| `Menu` | A button and the actions it opens, each of which may be disabled while it's being done |
| `SelectField` | A labelled choice among several, Base UI's Select on the menus' surface with the keyboard of a native select, which submits with its form |
| `FormField` | A control's label, hint and refusal, and the 28rem its width is capped at, which `TextField` and `SelectField` share |
| `Icon`, `Mark`, `Lockup` | One of the kit's own icons beside its word (ADR-0080); portalr's marks |

`gallery.screenshot.test.tsx` pins how they sit together, wide and narrow, in each scheme. It runs in CI alone, against Linux baselines.

Every area of a workspace renders in `AppShell`. The screens outside one are ui's `Plain` page: choosing a tenant or a workspace, with the account, and what went wrong, without it. Signing in is a card of its own. `admin` renders its frame, with its own mark.

## The wheel

Vite builds `app` and `admin` into `src/portalr/static/`, which git ignores and the wheel carries. portalr's `build` depends on theirs, and `ui-in-wheel`, in `check` and the release workflow, fails unless this version's wheel holds both, each with its typefaces, and the typefaces' licences, and each UI's third-party notices ([ADR-0033](adr/0033-third-party-notices-for-the-bundled-javascript.md)): the licences of the packages its bundle holds, written by its build, which fails on one the policy in `web/notices/policy.json` doesn't allow.
