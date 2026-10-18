# ADR-0080: Integrations on or off per workspace

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

The owner requires every integration to be switchable on and off for each workspace. [lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md) settled the port, `lattice_core.integrations.Integrations`, with grantr's store and lattice-core's `Defaults` without one, and declares forms', dashboards' and mini apps' keys, `ui:forms`, `ui:dashboards` and `ui:mini-apps`, the last off by default. [ADR-0081](0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md) gates the artifacts an integration governs: `Workspaces(gate=integration_gate(integrations, key_of))` refuses creating, editing, proposing and accepting while it is off, as `not_enabled`, and lets archives and rejections through. What is left to the forms is which artifact is whose, the agent's tools, and what the gate can't see.

## Decision

- **`ui_key_of(kind, data)`,** for `integration_gate`: a form and a submission to one are `ui:forms`', a dashboard `ui:dashboards`', and an app and a submission to one `ui:mini-apps`'. The application wires `Workspaces(gate=integration_gate(integrations, ui_key_of))`.
- **The keys are constants of `artifactr.ui.integrations`,** `FORMS`, `DASHBOARDS` and `MINI_APPS`, which name lattice-core's `KNOWN` entries: lattice-core declares them, and exports no constant for them.
- **`ui_tools(integrations=...)`** asks the port before each model request, through each tool's `prepare`: while forms are off, `ask_form` and `create_form` are left out of the request, their descriptions with them; while dashboards are off, `show_dashboard` and `update_dashboard`.
- **`ui_checks(integrations=...)`** refuses an answer to `ask_form` while forms are off, with `NotEnabled("ui:forms")`: an answer changes no artifact, so the gate never sees it. Everything else is the gate's.
- **The refusal is artifactr's `not_enabled`,** with the payload `{"type": "not_enabled", "message": "ui:forms is not available in this workspace", "integration": "ui:forms"}`, as for every integration. The wire schema names the forms' keys, `integration_key`, for a client that reads it.
- **Without an `Integrations`,** `ui_tools` and `ui_checks` ask lattice-core's `Defaults`: forms and dashboards on, mini apps off.
- **stackr's template passes none yet:** it wires no gate and no port for any integration, so an application it generates keeps the defaults.

## Options considered

| Option | For | Against |
|---|---|---|
| **The shared port and artifactr's gate, with the answer checked here (chosen)** | One refusal and one switch for every integration | An application wires the gate and the checks |
| A seam of the forms' own | Nothing to wire beside the forms | A second switch and a second refusal for portalr to read |

## Consequences

- Easier: forms, dashboards and mini apps switch from portalr's admin page as every integration does, and a client reads one refusal.
- Harder: an application that wires `ui_checks(integrations=...)` but no gate refuses only answers to `ask_form`.
- Revisit: mini apps' tools and their key, with RFC-0005's phase 2.
