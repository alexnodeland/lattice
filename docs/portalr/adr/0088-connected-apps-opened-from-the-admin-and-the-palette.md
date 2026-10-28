# ADR-0088: Connected apps, opened from the admin and the palette

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0084](0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md) (a place has links too; `deploymentAt` moves to the client), [ADR-0087](0087-a-command-first-layout-a-top-bar-a-palette-a-table-and-a-split-view.md) (the palette's groups), [ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md) (the integrations list), [stackr ADR-0042](../../stackr/adr/0042-a-generated-application-as-a-local-product.md) (`make tailnet`)

## Context

Integrations bring sidecar apps with a UI of their own: Plane and Vikunja beside the trackers, the craft apps' editors, Grafana, a ComfyUI-style tool. Admins and people use them, but nothing in the UIs opens them: you have to know their addresses (#871). They shouldn't become first-class in the app's navigation either, since whether they are there follows from which integrations are on.

A deployment is reached at more than one address, its loopback one and its tailnet name ([ADR-0084](0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md)), and a sidecar on its own port of `127.0.0.1` doesn't answer a phone on the tailnet.

The owner decided (2026-10-28): build it in v0.2; `make tailnet` follows the editors' port-sibling rule for the sidecars too; never 8443, never Funnel; the palette add-on's ceiling goes from 2,100 to 2,300 bytes for its group ([ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md)).

## Decision

- **`Site.links`, by integration key.** Each connected app's address, keyed by the integration that brings it (`tracker:plane`), any valid integration key of lattice-core's form (not checked against the registry, since an application may declare integrations of its own). The address is per deployment, so it is the site's, not the registry's: `KNOWN` names what an integration is, never where it runs. Each is held to the editors' rule, by the same code (`_urls`): a web origin as `lattice_core.origins.web_origin` checks it (https, or http on loopback only; no user or password, no wildcard, no IP address that isn't loopback), a plain path at most, no query or fragment. `_editors_apart` holds links too: none on a portal's origin, mini apps' or Supabase's. A bad link fails the start with its reason.
- **Beside each other origin, on its port.** `Place.links` is a link's address for a portal at an alias, and `beside(..., links=)` derives it by the port-sibling rule, as for the editors: `http://127.0.0.1:8090/` beside `https://<machine>.<tailnet>.ts.net` is `https://<machine>.<tailnet>.ts.net:8090/`. A link at an edge, with no port of its own, can't be beside another origin, and `beside` refuses it with its reason. `config.json` carries `links`, and each alias's `links`.
- **Resolved where the page is, in the client.** `deploymentAt(config, location.origin)` moves from the app to `@portalr/client`, since admin reads it too, and returns `links` beside the apps' origin and the editors: an alias's at an alias, the canonical ones at the canonical origin, none at an address the deployment doesn't name.
- **Admin: "Open" beside the switch.** In the integrations list, an integration that is on at the level shown and has a link gets an "Open" link under its switch: the kit's external `TextLink`, so `target="_blank"`, `rel="noopener noreferrer"`, the external mark, and a name of "Open <name> (opens in a new tab)". One that is off has none, so turning it off takes its link away.
- **The palette's "Connected apps" group.** After "Go to", one option per link whose integration grantr says is on in the workspace, "Open <name>", the name from the registry's sentence, with the external-link glyph and ", opens in a new tab" said after it. Following one (Enter, a click, a tap) closes the palette and opens the address with `window.open(url, "_blank", "noopener,noreferrer")`. Only grantr's answer counts: before it, or where it can't be read, no link is listed, never a default, so a member never sees a link to an app that isn't on for them. On a phone it is in the tab bar's search, under the areas, with the field empty. The group is the add-on's (about 145 bytes); the app's own chunks carry the links read and filtered (about 30 bytes of `initial`).
- **The tailnet: the port-sibling rule.** `make tailnet` serves each link's port on the tailnet name, beside the apps' and the editors', where `PORTAL_LINKS` puts it at `http://127.0.0.1:<port>`; it refuses before changing anything where a link is anywhere else, as it does for the editors. `scripts/tailnet.sh` already refuses 8443 in its plan, and never uses Funnel; nothing changes there.
- **Sign-in.** Each app keeps its own sign-in. There is no single sign-on, and the UIs say "Open", nothing more.
- **In the template,** `PORTAL_LINKS` is a JSON object like `FILES_EDITORS`, passed to `Site(links=)` and to `beside` for each of `PORTAL_EXTRA_URLS`.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where the address lives | **The site, by integration key (chosen)** | Per deployment, checked at the start, beside the other origins | A key to set per app |
| | A `url` on the registry's `Integration` | One place per integration | The registry is lattice's, the same in every deployment; an address isn't |
| Which state the palette trusts | **grantr's answer only (chosen)** | No link to an app that is off | No links until grantr answers |
| | The registry defaults, as the add-ons do | Links at once | A default-on app switched off would be linked for a moment, or while grantr is down |
| The tailnet | **Serve each loopback port beside the portal (chosen)** | The same rule as the editors; works from the phone | Each sidecar's port is on the tailnet |
| | Say the link works on the host alone | Nothing served | A link that fails on the phone |
| Where it shows in the app | **The palette (chosen)** | No first-class area; ~0 initial bytes | Found by searching |
| | An Apps area | Visible | Integration-specific tools become first-class |

## Consequences

- Easier: an admin or a member opens Plane or an editor from the UIs, from the laptop or a phone on the tailnet, without knowing its address.
- Harder: the palette add-on's ceiling is 2,300 bytes; its size at the time was 2,238.
- Harder: each sidecar's port is on the tailnet after `make tailnet`, as the editors' are; only for the tailnet, and only ports `PORTAL_LINKS` names.
- Deferred: a row on the workspace's home; links at an edge beside a tailnet, which need the places named explicitly, as for the editors.

## Action items

1. [x] `Site.links`, `Place.links`, `beside(links=)`, `config.json`; `deploymentAt` in the client.
2. [x] Admin's "Open"; the palette's group; tests that a link to an app that is off is never shown.
3. [x] The template's `PORTAL_LINKS`, and `make tailnet` serving each loopback link's port.
