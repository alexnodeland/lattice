# The admin UI

Admin, at `/portalr/admin/`, is the UI for a tenant's **owners and admins**: who has access, what changed, what people thought of the agent, what it costs, and what it did. An editor or a viewer who opens it is told there is no access. Operators have areas of their own, in [the runbook](operators.md).

Every area shows only where grantr allows its read, and every read names its tenant. Each area's page opens with its own state: a tool that is down or isn't configured fails that area's cards alone, and says so in a notice, a shape beside its words ([ADR-0023](../adr/0023-admins-shell-and-home.md), [ADR-0039](../adr/0039-elevation-status-colour-states-and-density.md)). Admin is compact: a table's rows are 36px high, where the app's are 44px. A chart's figures are also a table, under **Show the figures**, for a keyboard or a screen reader.

!!! info "What each area needs"

    `portalr:read_telemetry` for Feedback, Traces, Logs and Health; `portalr:read_spend` for Usage; for Access, the grantr action each part's changes take (`grantr:add_member`, `grantr:manage_groups`, `grantr:issue_key`, `grantr:define_role`, `grantr:grant`); `grantr:read_audit` for Audit; `grantr:manage_integrations`, on the tenant, for Integrations; `reflexr:read_runs` for Runs, and `reflexr:retry_run`, `reflexr:skip_run` and `reflexr:cancel_run` for its buttons. grantr's built-in `owner` role holds every one of these, and `admin` holds them too: it lacks only deleting the tenant. A test of these guides holds that against grantr's catalog.

## Home

Cards for the tenant: members, workspaces, feedback, failed turns and spend. Each is read on its own, and a card whose tool is unavailable or unconfigured says why and leaves the others. The spend card says **Near budget** at 80% of it and **Over budget** past it, each a word, a shape and a colour: gold, then red.

## Access

Where grantr's model is used: each part shows where its read is allowed, as a table or, on a phone, cards.

| Part | Does |
|---|---|
| Members | The tenant's members, people first. **Invite** by email (Supabase Auth creates or finds them, and grantr adds them), or add a service principal by name. Each is removed after a confirmation; no one is offered their own removal |
| Groups | Groups and their members |
| Keys | Keys for service principals. A key's secret is shown **once**, when it is issued; afterwards only its public id. Revoked after a confirmation |
| Roles | The built-in roles, and custom ones you define from the catalog's actions |
| Grants | Who holds which role on the tenant, a workspace or an item, given and revoked |

People are shown by email where the application passes `people` to the router ([Getting started](../getting-started.md#mount-the-router)): in Members and its remove dialog, Groups, Grants, and Audit. Without it, or for someone it can't name, a person is the first eight characters of their id, such as `3f2a91c4…`; a service principal is its id. Audit's filter by who made a change still takes an id, since the address holds ids only. The email you invite is sent to Supabase Auth and not logged, returned or kept; [Privacy](privacy.md#emails-and-names) says who sees whose email, and for how long it is held.

## Integrations

What the tenant and each of its workspaces offer beyond the basics: the trackers, WordCraft, forms, dashboards, mini apps, diagrams, math and Mermaid, each switched on or off ([lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md)). Choose **the tenant** or one of its workspaces at the top; the address keeps the choice, so a workspace's settings can be linked to.

Each integration's switch says whether it is on, with a badge (a filled circle for **On**, an outlined square for **Off**) and where that comes from:

| State | Means |
|---|---|
| Default | No one has set it here or on the tenant: it is what lattice's registry says. Mini apps and Mermaid are off by default; the rest are on |
| Inherited from the tenant | The tenant's setting, which a workspace follows until it sets its own |
| Set here | This level's own setting, with who set it and when; **Back to inherited** (on the tenant, **Back to the default**) unsets it |
| Off for the tenant | The tenant turned it off, so no workspace can turn it on: the switch is disabled |
| Not installed in this deployment | The deployment doesn't install it, so it is off everywhere: the switch is disabled |

A switch is saved at once, and disabled until grantr answers; the page then says what came of it. Each change is in [Audit](#audit) as "turned … on in workspace …", by whom; **See the audit log** opens it filtered to integrations switched. grantr decides what is on, and every library checks it again before it acts ([grantr ADR-0034](../../grantr/adr/0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md), [ADR-0045](../adr/0045-integrations-in-admin-and-the-apps-read-of-them.md)). A workspace's own admins hold the action on their workspace, but admin opens for a tenant's owners and admins alone, so they switch nothing here yet.

## Audit

grantr's log for the tenant, the newest on top, a sentence for each change with who made it and when ("added ci (service principal)", "granted viewer on notes to u_2"). Filter by type of change and by who made it; the filter is in the address, so a filtered log can be linked to. It reads a page at a time from the end.

## Feedback

People's thumbs per day, each evaluation's mean per day, each workspace's share and thumbs, and **what people said** in their comments. It reads Langfuse's scores for the tenant's traces, in a window of at most 91 days (the address keeps the window and a workspace), and says if it read only part.

## Usage

Spend per day against the tenant's LiteLLM budget, each day against its share of it where there is a budget, and each workspace's part from its `tenant-workspace:` tag, in a window of at most 91 days. A day near its share (80% or more) or over it is a level of the tracker, named in its legend, and the one over is hatched, so colour is never the only cue.

## Traces

The tenant's newest traces in the last hour, day or week, or one thread's or run's, from Tempo. A trace opens as a **tree of its spans** beside a waterfall: the arrow keys walk the tree, Left folds, Right opens, and a failed span is a word and a hatched bar. A trace read is bounded: 5,000 spans at most, and ten seconds from Tempo.

Spans show structure, timings and tokens. **What was said in a span, its prompt and completion, is not shown** until you ask for that span: [Privacy](privacy.md#traces) says what is withheld and how.

## Logs and Health

**Logs** lists the tenant's newest log records, in a window of at most 24 hours (1, 6 or 24), 1,000 at most, filtered by a thread or a run, in a virtualized list. A record shows its time, level, service, thread and run, and **the length of its line, not the line**; "Show this line" reads that one record's line when you ask. A line shows its ANSI colours from a fixed palette and nothing else of its escapes. If the read reached its limit it says there may be more.

**Health**, at the top of the same page, charts a turn's latency at the 95th percentile and the failed turns in each step, over the last hour, day or week, from Prometheus. It says the step of each point (1 minute, 15 minutes, 2 hours) and that times are UTC, and a step with no turns is a gap, not a zero.

## Runs

A workspace's rule runs, live from reflexr's stream, for the workspace you pick. The default is **Needs attention**: the *dead-lettered* runs (rules' runs that failed every attempt; not the workspace's list of events a rule couldn't evaluate, and not the bridge's) and the *retrying*. **Every state** shows all.

A failed or dead-lettered run is edged in red and a retrying one in gold, each with a shape and a word of its own. Each run offers **Retry**, **Skip** or **Cancel** as its state allows and grantr allows in that workspace. Each asks first, says what it does and what it can't undo, and takes an optional reason for Skip and Cancel. A command is sent once: the dialog can't be dismissed while it is under way, and a lost connection resends it under the same id, so the server carries it out once. A run lists **what people did to it**: who, when, why, from the log's own events. Only a run's reason code is shown, never its error message, which may hold what a person or a model said ([ADR-0032](../adr/0032-runs-in-admin.md)).

If reflexr can't be reached, the page says so after ten seconds of connecting (`PATIENCE` in `web/admin/src/runs.ts`), and keeps trying.

## Colour-blind friendly charts

**Colour-blind friendly charts** is a switch in the account menu, under **Colour**, in this UI and in the app. It is a setting of this browser: it is kept in the browser's local storage as the scheme is, so it is not shared with the person's other browsers or devices, and it is applied before the page first paints, so it never flashes on after the page. With it on, the charts' series take a blue, an orange or yellow and a purple that stay apart to people who see no red, no green or no blue, and every series past the first is hatched, dashed in a line and marked with a shape of its own, so no series relies on its hue ([ADR-0036](../adr/0036-the-chart-theme-and-colour-blind-mode.md)). The status colours are the same in both modes: they hold their contrast to every reader, and each status is a word and a shape too. In a high-contrast mode (forced colours) the patterns are on whatever was chosen.

## What is not built

- **Deleting a tenant, or granting an operator,** from admin: those are grantr's, from its API or `make operator`.
