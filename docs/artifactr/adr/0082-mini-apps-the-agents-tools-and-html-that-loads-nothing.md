# ADR-0082: Mini apps: the agent's tools, and HTML that loads nothing

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland
**Amends:** [ADR-0078](0078-the-agents-toolset-for-forms-and-no-apps-yet.md), which left apps out of the toolset, and the revisit in [ADR-0080](0080-integrations-on-or-off-per-workspace.md) of mini apps' tools

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)'s second phase runs mini apps: one HTML file an agent writes, run for everyone who opens the thread, sandboxed on an origin of its own, loading nothing, and no person reviewing it first (its Decision O6). Phase 1 defined the `app` kind and its limits, and its checks already hold that only an agent makes an app and a person changes only its `state` ([ADR-0075](0075-forms-refused-at-the-boundary-through-the-checks.md)); no agent was offered a tool to make one ([ADR-0078](0078-the-agents-toolset-for-forms-and-no-apps-yet.md)). The integration, `ui:mini-apps`, is declared by lattice-core and off by default ([ADR-0080](0080-integrations-on-or-off-per-workspace.md)).

The policy portalr runs an app under is what keeps it from loading anything. The RFC also asks artifactr.ui to refuse an app whose HTML names an external URL, as a first filter, so a model that wrote a script from a CDN or a web font learns of it at once, rather than from a blank frame.

## Decision

- **`ui_tools(apps=True)` offers `create_app(title, summary, html)` and `update_app(id, html, summary=None, title=None)`,** each only while `ui:mini-apps` is on in the run's workspace, asked through its `prepare` as forms' and dashboards' tools are. Off, as it is by default, they are left out of every request, descriptions and all. `update_app` makes the next version with the HTML, and the summary when one is given; the app's `state` is kept. The RFC named the first `make_app`; the owner named it `create_app`, after `create_form`.
- **`AGENT_TYPES` stays `(Form, Dashboard)`,** so `ArtifactWorkspace`'s generic tools never make or edit an app: only these two tools do, and only while apps are on.
- **The tools' description is the bridge's contract,** the shapes portalr's host speaks, as RFC-0005's U4 has it: JSON-RPC 2.0 over `window.parent.postMessage`, on MCP Apps' method names (`ui/initialize`, `tools/call`, `ui/open-link`, `ui/notifications/size-changed`, and `ui/notifications/host-context-changed` from the host), with three tools, `get_state`, `set_state` (a JSON Patch on the app's state) and `submit` (values sent as the person's submission once they confirm), and their limits in words. It never changes between requests. *Amended 2026-10-20:* it names the reply shapes, a result's `structuredContent` or, refused, `isError: true` with none, and asks an app to draw everything from one state in one `render()` after every change, since a generated game that rendered before its turn changed left its board disabled.
- **An app's HTML loads nothing,** or the agent's tools refuse it, as a retry, and `ui_checks` refuse it as `ValidationFailed` at `["data", "html"]`, as an app is made or its HTML changed, with each place named: "the HTML loads from outside the app, which can load nothing: write what it needs inline, or as a data: URL, and open links with ui/open-link (`<script src>`: https://…)". The filter is not the `App` type's: a type's data is validated on every read, so a filter that grows stricter would make apps that exist unreadable, and every read would pay for it. `artifactr.ui._html` reads the markup with the standard library's tokenizer, as a browser does. A URL is the app's own when it is empty, or starts with `#`, `data:`, `javascript:`, `mailto:`, `tel:` or `about:blank`; anything else, a relative path included, would be fetched from the apps' origin or beyond, which serves nothing to an app. Scripts are not run: what one builds at run time is the policy's to refuse, and words such as a URL in a paragraph load nothing. It refuses:

  - a URL in an attribute that loads or goes somewhere (`src`, `href`, `action`, `formaction`, `poster`, `data`, `background`, `icon`, `manifest`, `xlink:href`), or in one that lists URLs (`srcset`, `imagesrcset`, `ping`), split as a browser splits them;
  - a URL in CSS, a `style` element's or attribute's `url()`, `@import` or `image-set()`;
  - a script's static import from another origin (`from "https://…"`, `import("//…")`), and a URL in an import map;
  - what a frame's `srcdoc` would load, read the same way;
  - a `<meta http-equiv="refresh">`.
- **`set_state`'s pace is the host's.** The RFC coalesces a frame's state to at most one version every five seconds. A revision carries no time, and a check that refused a version too soon after the last would refuse a second person using the same app, so portalr's host coalesces, and stops answering a frame past 60 messages a minute. artifactr holds what a write may be: a person's edit of an app changes only its `state`, and is refused by the gate while mini apps are off ([ADR-0081](0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md)).
- **One app is switched off by archiving it.** A submission to an archived app is refused as closed ([ADR-0075](0075-forms-refused-at-the-boundary-through-the-checks.md)), core refuses an edit of an archived artifact, and portalr runs none. The deployment's and a tenant's switches are the port's, `ui:mini-apps` set from portalr's admin.

## Options considered

| Option | For | Against |
|---|---|---|
| **The filter in the tools and the checks, over the markup, its CSS and a script's imports (chosen)** | Every write refuses alike; a model learns what to inline; apps that exist still read when the filter changes; no dependency | Can't see what a script builds at run time, which the policy refuses |
| The filter in `App`'s validator | One place | Run on every read; a stricter filter makes existing apps unreadable, archiving them included |
| A regular expression over the whole HTML for `://` | Simpler | Refuses a URL in words or in a script's string, and misses `//host` and relative paths |
| No filter, the policy alone | Nothing to keep | A model learns of a CDN script only from an app that draws nothing |
| **Pacing in the host (chosen)** | Two people can use one app; what the RFC says | A client of artifactr's other than portalr can write faster |
| A check that refuses a state too soon after the last | Holds for every client | Revisions carry no time; refuses a second person; a check holds no lock |

## Consequences

- Easier: an application that already wires `ui_tools(integrations=...)`, as stackr's template does, offers apps the moment a workspace switches `ui:mini-apps` on, and not before.
- Harder: a link in an app's markup is refused; it opens one through `ui/open-link`, from its script, once the person confirms it.
- Harder: a client other than portalr's host can write an app's state as often as a person may edit it.
