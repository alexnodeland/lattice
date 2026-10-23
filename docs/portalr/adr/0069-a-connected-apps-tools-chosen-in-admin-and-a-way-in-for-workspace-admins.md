# ADR-0069: A connected app's tools chosen in admin, and a way in for a workspace's admins

**Status:** Proposed
**Date:** 2026-10-23
**Deciders:** Alex Nodeland
**Amends:** [ADR-0067](0067-settings-in-admin.md), whose page was the tenant's admins' alone and had a field for numbers only; implements the screen of artifactr [ADR-0089](../../artifactr/adr/0089-a-connected-apps-tools-narrowed-per-workspace.md) and closes [#627](https://github.com/alexnodeland/lattice/issues/627)

## Context

artifactr ADR-0089 adds a `Subset` setting per connected app, `connect-tools:<app>`: the tools a workspace offers, narrowed below the operator's. ADR-0067's page shows a setting of names read-only. grantr already lets a workspace's admins narrow their own workspace's settings, but the page let in only those who hold `grantr:manage_settings` on the tenant.

## Decision

- **A setting of names is a group of checkboxes**, the kit's `CheckboxGroup`, named after the setting ("FreeCAD's tools").
  - Each tool is labelled with its name and its risk in words ("get_view (reads)", "execute_code (runs code)"). The risk words come from grantr, which reads each setting's `labels` from lattice-core's registry (`CONNECTED_TOOL_RISKS`), so admin hard-codes none.
  - A tool the layer above doesn't offer can't be checked: it is shown disabled and described "Not offered above". This uses two new optional parts of the kit's checkbox choice, `disabled` and `description`.
  - Save, unsetting, `If-Match`, refusals, a 409 and the focus all work as they do for a number (ADR-0067). The two kinds share one row.
- **Anyone who may narrow a setting somewhere in the tenant finds the page** (#627).
  - One read of grantr's checks asks about `grantr:manage_settings` on the tenant and in each of its workspaces, up to 99 of them. The page opens for anyone who holds it anywhere.
  - "Where" lists only the levels the reader holds it at. A workspace's admin who doesn't hold it on the tenant starts in their first workspace.
  - A workspace named in the address that the reader doesn't administer says so, and shows nothing of it.
  - The rail shows Settings for a tenant's admins as before. For a workspace's admin, it shows Settings once a page has read the tenant's workspaces, as Home does. The rail reads none itself, so pages that don't need the list don't pay for it.

## Consequences

- Easier: a workspace's admin narrows their workspace's tools and limits from admin, not the API.
- Harder: the page's way in is one more read of grantr's checks, made once per tenant and cached.
- The kit's checkbox choice gains `disabled` and `description`. The app's bundle grows by a few bytes for them.
