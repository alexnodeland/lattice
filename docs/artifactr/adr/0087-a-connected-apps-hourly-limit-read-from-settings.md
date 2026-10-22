# ADR-0087: A connected app's hourly limit, read from settings

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Amends:** [ADR-0085](0085-connected-apps-an-operators-own-freecad-or-blender-through-a-vetted-mcp-server.md), whose limit was the operator's alone

## Context

ADR-0085 limits each workspace's tries at a connected app's code and network calls per hour, through `Connection(per_hour=...)`, a number or the application's answer. lattice [ADR-0030](../../adr/0030-settings-typed-declared-in-lattice-core-and-only-narrowed-below.md) adds settings that tenant and workspace admins may only narrow.

## Decision

- **`per_hour_setting(settings, app)`** is a `PerHour` that reads `connect-per-hour:<app>` from a `Settings` port, such as grantr's `Grants`, on every call, with no cache. An application passes it as `Connection(per_hour=per_hour_setting(grants, "freecad"))`. The operator's value lives in grantr's `operator_settings`, and admins narrow it from there.
- **It fails closed.** Any failure to read the limit counts as a limit of 0, so the call is refused rather than run uncounted. That covers:
  - a store that raises;
  - a key the store doesn't declare;
  - a value that isn't a number.

  grantr's own port already answers 0 while its store can't be read.
- **The limit is per app within a workspace**, as the key says. A connected app vetted later needs its key added to lattice-core's registry before its limit can be set.
- An integer `per_hour` keeps working, as the code's own value.

## Consequences

- Easier: an admin lowers a workspace's limit for one app without a deploy.
- Harder: a deployment that forgets the setting's key for a new app gets the floor, 0, and no code calls, until the registry declares it.
