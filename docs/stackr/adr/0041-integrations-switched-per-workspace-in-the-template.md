# ADR-0041: Integrations switched per workspace in the template

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Wires [lattice ADR-0027](../../adr/0027-integrations-switched-per-workspace-through-one-port.md)'s port into a generated application, the last seam grantr's guide lists under "Adopting the port" ([grantr's guide](../../grantr/guides/integrations.md)). Amends [ADR-0040](0040-forms-and-dashboards-in-the-template.md), which left forms and dashboards at their defaults until this.

## Context

lattice's integrations each ask lattice-core's `Integrations` port before they act in a workspace, and grantr's `Grants` answers it from the deployment's `installed`, the tenant's switch and the workspace's. The template has three of them: forms and dashboards (`ui`), a tracker (`tracker`), and, with the portal, the Markdown add-ons portalr's UIs ask about. Until now it gave `Grants` no `installed`, which installs every integration lattice declares, and wired no integration to the port: none could be switched off.

## Decision

- **The application installs what it ships,** `INSTALLED` in `access.py`, which `build_grants` gives `Grants(installed=...)`, so `make tenant` and the admin commands see the same: `tracker:<tracker>` with a tracker; `ui:forms` and `ui:dashboards` with `ui`; and `markdown:math` with the portal, which typesets formulas where it is on. Any other is off everywhere, and portalr's admin lists only these to switch. `ui:mini-apps` is RFC-0005's second phase, so a mini app's `app` artifact is refused as `not_enabled`; `markdown:mermaid` is parked while Mermaid can't draw under portalr's policy; `files:wordcraft` and `excalidraw` have nothing in the template to govern.
- **One `integrations` for every part.** `create_app` passes `access.grants` with grantr, and lattice-core's `Defaults` without it, where each integration keeps its default and none can be switched. `Collaboration` gives it to `ui_checks`, to the notes agent's `ui_tools`, and to artifactr's `Workspaces(gate=integration_gate(integrations, ui_key_of))`; `Tracking` gives it to relayr's `Trackers` (relayr ADR-0033's amendment). `ui_key_of` is the only `key_of` the template needs: forms and dashboards are its only integrations that govern artifacts by their kind.
- **lattice-core is a dependency of its own** where the application imports the port, from lattice at the rendered commit like the libraries ([ADR-0018](0018-the-template-pins-the-libraries-at-its-own-commit.md)); `use_integrations`, derived from `ui` and `tracker`, says where.
- **The generated tests switch each off over grantr's admin API,** as an admin would: a form made in a workspace with forms off is refused as `not_enabled`, and one in another workspace is made; a tracker off in a workspace files nothing there, and the run that tried is dead, since it isn't allowed. Without grantr there is nothing to switch, and the tests that run then are unchanged.

## Options considered

| Option | For | Against |
|---|---|---|
| **Install what the application ships (chosen)** | Admins see the integrations that do something; one the template adds later is installed with its code | A key added to lattice's registry is off in a generated application until the template installs it |
| Install every integration (`installed` omitted) | No list to keep | portalr's admin lists switches that govern nothing, mini apps among them |
| `Defaults` in place of grantr's answer with grantr too | Nothing is switched by accident | Admins' switches would do nothing |

## Consequences

- Easier: a tenant's or workspace's admin switches forms, dashboards and the tracker from portalr's admin, and every surface and the agent's runs follow.
- Harder: each check of a form, a dashboard or a tracker's write reads grantr's table first; grantr's guide says an application that asks often caches.
- To revisit: the list in `INSTALLED` grows with each integration the template ships.
