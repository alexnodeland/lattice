# ADR-0080: Integrations on or off per workspace

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

The owner requires every integration to be switchable on and off for each workspace. Nothing in lattice keeps a workspace's settings:

- **grantr** keeps tenants, members, groups, roles, grants and restricted items; nothing about what a workspace offers.
- **portalr's admin** reads and changes what grantr keeps, feedback, traces and spend; it has no settings of its own to toggle.
- **reflexr's stored rules** have an `enabled` flag per rule, not per workspace or integration.
- **relayr** has allowlists per rule, and its followers start for every workspace opened.
- **artifactr** has the nearest shape: `GuardrailPolicy`, a port the application answers per workspace.

One shared `Integrations` port, with its store by deployment, tenant and workspace, audited and with a page in portalr's admin, is being designed apart, in an RFC of its own, for every integration alike. artifactr's forms need a seam that store can fill unchanged, and nothing more.

## Decision

- **A protocol, `Integrations`, in `artifactr.ui.integrations`:** `async def is_enabled(self, tenant_id, workspace_id, key: str) -> bool`. It is generic, a key string per integration, so it moves to the shared home unchanged, and the shared store implements it.
- **The forms' keys are constants:** `FORMS = "ui:forms"`, `DASHBOARDS = "ui:dashboards"` and `MINI_APPS = "ui:mini-apps"`. With no `Integrations` injected, forms and dashboards are on and mini apps off (`DEFAULT_ON`); mini apps are RFC-0005's second phase, and nothing offers one in the first.
- **Where it is consulted:**
  - `ui_tools(integrations=...)` asks before each model request, through each tool's `prepare`: while forms are off, `ask_form` and `create_form` are left out of the request, their descriptions with them; while dashboards are off, `show_dashboard` and `update_dashboard`.
  - `ui_checks(integrations=...)` refuses an integration's new commands while it is off: with forms off, a new form, a submission to a form and an answer to `ask_form`; with dashboards off, a new or changed dashboard. What exists still reads, and portalr shows it read-only; a form's author still closes it.
- **The refusal is `FeatureOff`,** an `invalid_state` whose payload adds `{"reason": "off", "key": "ui:forms"}`, the key of the integration that is off; the wire schema names the keys as `integration_key`, beside `refusal_reason`.
- **No store here.** The shared port's store, its audit and its admin page are the shared RFC's.
- **stackr's template injects none yet:** an application it generates keeps forms and dashboards on until the shared store exists, and one that needs a switch now implements the protocol.

## Options considered

| Option | For | Against |
|---|---|---|
| **A generic protocol, filled by the shared store (chosen)** | No store built twice; moves unchanged | Each application implements it until the store exists |
| A callable per integration's own features | Smallest | Every integration's shape differs, and the shared store adapts to each |
| A store in artifactr | Works today, alone | One store per integration, each with its own security and audit |

## Consequences

- Easier: an application switches forms or dashboards per workspace now, and the shared store later implements the same protocol.
- Harder: it is asked on every model request and every command of its integrations, so an implementation caches what it reads.
- Revisit: when the shared `Integrations` RFC lands, its port replaces this protocol's home, and mini apps' default with phase 2.
