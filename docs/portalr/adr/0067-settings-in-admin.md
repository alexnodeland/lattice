# ADR-0067: Settings in admin

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Beside:** [ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md), integrations in admin; implements the screen of lattice [ADR-0030](../../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md)

## Context

lattice ADR-0030 lets a tenant's and a workspace's admins lower settings, never raise them. grantr stores the values ([grantr ADR-0035](../../grantr/adr/0035-settings-narrowed-per-tenant-and-workspace-in-grantrs-table-versioned-audited.md)). The owner decided that settings get a page of their own in admin, separate from Integrations.

## Decision

- **A Settings page per tenant,** `/t/$tenant/settings`, on the tenant's rail for those who hold `grantr:manage_settings` on the tenant. Anyone else finds nothing there. grantr also lets a workspace's admins lower their own workspace's settings; in v0.2 they do so through grantr's API, and the page says so. A workspace-scoped way in is a follow-up ([#627](https://github.com/alexnodeland/lattice/issues/627)). As on Integrations, the level is the tenant or one of its workspaces, chosen at the top and kept in the address (`?workspace=`).
- **One kit `Row` per setting:**
  - its name, from what it limits ("FreeCAD's tries an hour"), from a table of labels by key (`LABELS`), never the key itself. A test holds that every setting lattice-core declares has a label;
  - the registry's sentence;
  - what applies, and the ceiling with the layer that sets it ("At most 20: the tenant's value");
  - what is set at this level, by whom and when;
  - if what is set no longer applies (clamped), a sentence saying why: a layer above, or the settings, now allow no more; or the settings now allow at least their new lowest, which applies.
- **A labelled number field** for each setting, named after it, with a hint giving the range this level may set (from the lowest to the ceiling).
  - **Save** sends the value with the version read, as `If-Match`.
  - **Use the tenant's**, **Use the operator's** or **Use the default** unsets it.
  - Both buttons are named for their setting, so no two on the page share a name.
  - Each row stays mounted while its setting is read back, so the focus stays where it was. After an unset, whose button goes, the focus moves to the field.
  - A send is made once: a second Save, or Enter, while one is under way does nothing. The buttons stay focusable while disabled.
  - What a change did is said in a status region that is on the page, empty, before anything is said, so screen readers announce it as it changes.
- **Refusals:**
  - Text that isn't a whole number within the bounds is refused on the field before grantr is asked.
  - grantr's refusal of a value (422) or a caller (403) is the field's error, in grantr's words, with the key named as the page names the setting. The focus moves to the field, whose description carries the error, so it is read out there.
  - Admin shows grantr's words because an admin needs the ceiling and the layer that sets it to act; the screens tenants' people use show a status and a known reason only ([ADR-0065](0065-empty-error-and-not-found-states.md)). Any other status is a plain sentence saying the server couldn't do it.
  - A version someone changed first (409) is said in a warning that takes the focus. The warning says what is set now and what applies, and that the value tried wasn't saved. The field keeps the value tried.
- **Keys no registry declares** are listed in a note, as never applied.
- **The heading takes the focus as the page appears** (`PageHeader focus`), so a reader who follows a link in admin starts at its top: the first part of the accessibility audit's rule that focus moves to a page's `h1` on a route change.
- **Kit components and brand tokens only.** The style census and admin's size budget are unchanged.

## Consequences

- Easier: an admin lowers a connected app's limit for a tenant or a workspace without a deploy, and sees why a value applies.
- Harder: each new kind of setting, such as PR 3's per-tool subsets, needs its own field on this page.
