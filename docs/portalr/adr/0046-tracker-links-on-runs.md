# ADR-0046: Tracker links on runs

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland

Builds phase 3 of [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md), [portalr, later](../../rfcs/0004-relayr-and-task-trackers.md#portalr-later): a run shows the tracker items it was filed as, and the item a `tracker:` event was about links to it. relayr's side is [relayr ADR-0039](../../relayr/adr/0039-the-tracker-connectors-reads-for-the-portal.md).

## Context

The RFC speaks of "a run's page" and "a tracker event's page". portalr has neither: the app's runs and admin's are rows in a list ([ADR-0018](0018-the-runs-area-and-feedback.md), [ADR-0032](0032-runs-in-admin.md)), and no screen shows an event of the log by itself. relayr keeps what a run filed by the run's chain, not by its id; the app's reflexr stream carries every event, `tracker:` ones among them, and admin's asks for run events alone, so the bodies of the application's events never reach it (ADR-0032). A `tracker:` event carries its item's name and link; what it says of the item, a title or a comment, is what a person wrote in the tracker.

## Decision

- **On the run's row, in both UIs,** under its rule: **Filed as**, the items its chain filed or commented on, from relayr's read of what the workspace's runs filed, matched by the chain the run's `run_started` envelope names; and, in the app, **From**, the items whose `tracker:` events its firing matched. A run's row is where a run is shown; a page of its own would hold nothing else yet. admin has no **From**: its stream asks for run events alone, and stays so.
- **The store keeps each run's chain,** and, for each `tracker:` event, its item's tracker, name and link, by `seq`, and for each firing the items it matched, each once: never what the event said. Only an event whose actor is relayr's followers' source, `tracker`, names an item: the namespace is reserved to it only where the application passes reflexr `publishers=`, and a link anyone else published could lead anywhere under a tracker's name. An event that names no item, or whose fields aren't strings, is ignored as other events are.
- **One read per workspace,** `queries.relayr.filed`, made stale when an attempt ends: a run succeeding, retrying or dead-lettered, after which it may have filed something. With no relayr surface it answers none, and nothing is asked.
- **Where relayr is** is `config.json`'s `surfaces.relayr`: an origin, as grantr's is, since relayr's paths carry `/relayr/v1`; `null` by default, for an application without a tracker.
- **The kit's `TrackerItems`** draws them: a label, then each item as a link that opens in a new tab with `rel="noopener noreferrer"`, named aloud as "OPS-12, in Plane, opens in a new tab", with an icon beside the name; an item a person deleted is its name struck through and *deleted* in words; an address that isn't http or https is a name and never a link. `safeHref`, which Tools wrote for its links ([ADR-0035](0035-tools-and-the-record-of-opening-them.md)), moves to the kit for it. Opening a link is not recorded: unlike Tools' links, it leads past no gate of portalr's, and the tracker checks its own access.
- **The switch doesn't hide them.** `tracker:plane` or `tracker:vikunja` off in a workspace stops relayr filing and reading there; what was filed stays filed, and its link still opens.
- **Scenarios run against a fake tracker** in the test application: a triage run that is dead-lettered is filed, keyed by the run, by `portalr:file-dead-letter`; `POST /tracker/edits`, which only the test application has, renames an item as a person would, and `portalr:follow-up` runs on the change. `trackers.feature` has a scenario for each link, the RFC's exit criterion for the phase.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where | **The run's row (chosen)** | Where runs are; no new route | A row carries more |
| | A page per run, and per event | The RFC's words | Pages with one line each; an event page would show what a person wrote in the tracker |
| Matching a run | **By its chain (chosen)** | What relayr records; a later run of the same rule that comments on the item shows it too | Every run of a chain shows the item, the failed run and the one that filed it alike |
| | By run id | Exact | relayr keeps no run id on the key, and a chain is the item's story ([relayr ADR-0021](../../relayr/adr/0021-chains-continue-across-the-bridge.md)) |
| admin's **From** | **None (chosen)** | Its stream stays to run events | A run in admin doesn't say a tracker set it off |
| | Ask for `tracker:` events too | The link | What people wrote in the tracker would reach admin's browser |

## Consequences

- A run filed in a tracker links to the item from both UIs, and a run a tracker's change set off links to it from the app, with no request per run.
- `config.json` grows `surfaces.relayr`, and the client a typed relayr client, from relayr's committed document.
- An application must mount relayr's reads and name them in `Surfaces(relayr=...)` for the links to show; stackr's template doesn't yet.
