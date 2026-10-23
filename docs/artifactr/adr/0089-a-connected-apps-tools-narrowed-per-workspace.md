# ADR-0089: A connected app's tools, narrowed per workspace

**Status:** Proposed
**Date:** 2026-10-23
**Deciders:** Alex Nodeland
**Amends:** [ADR-0085](0085-connected-apps-an-operators-own-freecad-or-blender-through-a-vetted-mcp-server.md), whose tools were the operator's alone; beside [ADR-0087](0087-a-connected-apps-hourly-limit-read-from-settings.md)

## Context

ADR-0085 offers a connected app's `read` and `edit` tools wherever the app is switched on, and its `code` and `network` tools only where the operator allows each by name. The owner decided (2026-10-22) that a workspace may narrow these by tool, as a setting tenants and workspaces may only narrow (lattice [ADR-0030](../../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)). For that to mean anything, the operator also needs a way to withhold `read` and `edit` tools.

## Decision

- **The operator's layer is `Connection(offer=..., allow=...)`.**
  - `offer` names the `read` and `edit` tools the operator offers; every one by default. Naming any other tool is refused as the connection is made.
  - `allow` names the `code` and `network` tools, as before.
  - Together they are the most any workspace offers.
- **Each app has a `Subset` setting, `connect-tools:<app>`,** declared in lattice-core and settable down to the workspace.
  - Its universe is every tool the vetted entry names, other than `host` tools. lattice-core holds it as `CONNECTED_TOOLS`, since it can't import artifactr.
  - An artifactr test holds the two lists equal. When it fails, its message names the file to edit.
  - Its default is the whole universe, so nothing changes until someone narrows it.
- **`Connection(tools=tools_setting(grants, app))` reads it.**
  - The tools a workspace offers are the operator's `offer` and `allow`, intersected with the setting.
  - The setting is read with no cache at each listing, and again at each call: a tool narrowed out between the two is refused at the call.
  - The app's switches (`connect:<app>`, `connect-code:<app>`) and the person's action still gate as before. The setting only ever removes more.
- **It fails closed.** A setting that can't be read, or isn't names, offers no tools, at the listing and at the call alike.
- **Wiring it is the application's.** For the setting to narrow from the operator's layer, the operator's value in grantr's `operator_settings` is the same list as `offer` and `allow` together. Otherwise it narrows from the registry's default, and the intersection with `offer` and `allow` still holds.

## Consequences

- Easier: a workspace offers FreeCAD's reads without `create_object`, or a code tool without the others, with no deploy.
- Harder: a tool vetted later is added in two places, which the test enforces.
- Follow-ups: the admin page's checkboxes for these settings, with a way in for a workspace's admins (#627).
