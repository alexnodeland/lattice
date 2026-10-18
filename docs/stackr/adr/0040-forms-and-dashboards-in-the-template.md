# ADR-0040: Forms and dashboards in the template

**Status:** Accepted, amended by [ADR-0041](0041-integrations-switched-per-workspace-in-the-template.md)
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Builds stackr's row of [lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)'s phase 1: the template's `ui` question, which wires artifactr's forms and dashboards ([`artifactr.ui`](../../artifactr/guides/forms-and-dashboards.md), behind `artifactr-ai[forms]`), their types, toolset and checks, and relayr's projections of them (`relayr.ui`), into a generated application.

## Context

`artifactr.ui` lets an agent ask a form, which pauses its run until a person answers, make a form that takes submissions without a run waiting, and show a dashboard. An application wires it in four places: its types in artifactr's `Workspaces` and in the agent's `ArtifactWorkspace`, its checks in `Workspaces(checks=...)`, its toolset on the agent, and, with relayr, `relayr.ui`'s projections in the followers and its events and publishers in reflexr's `Workspaces`. Two things were open.

- **Who administers a form.** The checks let only a form's author change its `schema` or close it, or whom the application's `is_admin` allows; artifactr can't import grantr, so the application answers it ([artifactr ADR-0075](../../artifactr/adr/0075-forms-refused-at-the-boundary-through-the-checks.md)). grantr's catalogs have no action that means "administers forms".
- **Whether it is on by default.** The template's other optional parts, `evals`, `bridge` and `portal`, are.

## Decision

- **A `ui` question,** asked only when the application has artifactr, **on by default**, as the other optional parts are. `use_ui` is the derived answer the files read, so an application on reflexr alone never has it. Without it, the application is as it was.
- **It is an extra of the libraries the application has already:** `artifactr-ai[forms]`, and `relayr-ai[forms]` when the bridge is on, from lattice at the commit the template was rendered from ([ADR-0018](0018-the-template-pins-the-libraries-at-its-own-commit.md)), or from `libraries_path` in lattice's own checks.
- **The types are registered as `artifactr.ui` documents:** all of `UI_TYPES` in `Collaboration`'s `Workspaces`, so every kind a person or the agent sends is read and checked, and `AGENT_TYPES` (`form` and `dashboard`) beside `note` in the notes agent's `ArtifactWorkspace`, the kinds its own tools write. A `submission` is a person's and an `app` is defined and not offered: portalr shows an app's label and summary alone in phase 1.
- **The toolset is `artifactr.ui`'s defaults,** `ui_tools()`: `ask_form`, `create_form`, `show_dashboard` and `update_dashboard`. The notes agent's `output_type` already includes `DeferredToolRequests`, which `ask_form` needs. Apps are RFC-0005's phase 2, and the toolset has no parameter for them yet ([artifactr ADR-0078](../../artifactr/adr/0078-the-agents-toolset-for-forms-and-no-apps-yet.md)). Its instructions gain one line: ask with a form for several answers at once, and show figures as a dashboard.
- **The checks are `ui_checks()`;** with grantr, `is_admin` is `Access.administers`: **whoever may `grantr:restrict` on the workspace**, which its admins and the tenant's owners and admins hold and its editors and viewers don't. That is grantr's existing notion of who governs what is in a workspace (who may hide a thread or an artifact), so the template adds no action to a catalog and `access.md` is unchanged. The actor is mapped to grantr's subject as every other check maps it, so a person's agent run is checked as the person. Without grantr, there is no `is_admin`, and only a form's author changes it.
- **The `Integrations` port and artifactr's gate are not wired,** for the forms as for every other integration the template has: forms and dashboards keep their defaults, on, until the template wires lattice ADR-0027's port and artifactr ADR-0081's gate for all of them ([artifactr ADR-0080](../../artifactr/adr/0080-integrations-on-or-off-per-workspace.md)).
- **With the bridge,** relayr's followers take `Projections(**UI_PROJECTIONS)`. The template has no projections of its own, so `relayr.ui`'s are the whole set; an application that adds its own merges each mapping with them. reflexr's `Workspaces` accept `UI_EVENTS` and reserve the `ui` namespace to the follower with `UI_PUBLISHERS`, beside `artifactr`'s, so no client publishes a `ui:form_submitted` itself. `ui:form_submitted` is then among the event types rules from chat are checked against, so a person may draft a rule on it.
- **No example rule on `ui:form_submitted`.** The incident timeline is the template's example of a rule acting in artifactr; a second would be code every application deletes. The generated tests check that the event reaches reflexr instead.
- **It is checked as everything in the template is.** `check-template` renders eighteen variants, one of them without `ui`, and CI's Template job runs that one's `make check` too. The generated tests: the notes agent asks a form, an answer that doesn't fit the schema is refused, and the run resumes with the one that does (`test_collaboration.py`); with grantr, an editor can't close a form someone else made and the tenant's admin can (`test_access.py`); with the bridge, a submission to a form reaches reflexr as `ui:form_submitted` and a client's forged one is refused (`test_bridge.py`).

## Options considered

| Option | For | Against |
|---|---|---|
| **`is_admin` as `grantr:restrict` on the workspace (chosen)** | An action grantr already has, held by exactly the workspace's admins and the tenant's owners and admins | It ties closing a form to restricting, which a role could separate only by a new action |
| No `is_admin` | Nothing to explain | No one but its author can close a form, however a workspace is run |
| A new action, such as `artifactr:administer` | Says what it means | A change to artifactr's catalog and every role for one template's check |
| **On by default (chosen)** | As the template's other optional parts are; forms and dashboards are phase 1's whole point | An application updated with `copier update` gains four tools on its agent unless it says no |
| Off by default | An updated application is unchanged | Unlike every other optional part |

## Consequences

- Easier: `copier copy` gives the notes agent forms and dashboards, checked before they commit, and, with the bridge, an event for rules from either way of asking.
- Harder: the notes agent has four more tools in its prompt.
- Not done: apps, RFC-0005's phase 2, which adds `apps.<host>` at the edge and the apps setting; and portalr's renderers, which phase 1 builds in portalr, not here.
