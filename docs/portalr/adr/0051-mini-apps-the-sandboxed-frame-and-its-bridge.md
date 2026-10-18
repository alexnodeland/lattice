# ADR-0051: Mini apps: the sandboxed frame and its bridge

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland
**Amends:** [ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md)'s ceiling for the app's total

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md)'s second phase runs mini apps: one HTML file an agent wrote, run for everyone who opens it, with no person reviewing it first (its Decision O6). The sandbox and its policy carry the whole weight, so each layer assumes the one before it failed. artifactr.ui offers the agent `create_app` and `update_app` while `ui:mini-apps` is on, refuses HTML that names anything to load, and lets a person change an app's `state` and nothing else ([artifactr ADR-0082](../../artifactr/adr/0082-mini-apps-the-agents-tools-and-html-that-loads-nothing.md)). Its tools' description is the bridge's contract, on MCP Apps' method names, as the RFC's U4 has it: portalr's own host, not `@modelcontextprotocol/ext-apps` or `@mcp-ui/client`.

The RFC left the browser's behaviour unverified. A spike in Chromium, with the portal, the apps' origin and a sink each a real origin on 127.0.0.1, settled it:

- **An inner `srcdoc` frame inherits the sandbox's policy.** With the sandbox's script allowed by its hash, as the RFC wrote, the app's own inline scripts were refused too: nothing ran.
- **`frame-src 'none'` doesn't stop a `srcdoc` frame,** which isn't fetched, and does stop the app's frame navigating itself to another address, the likeliest way out: `location.href`, a link it clicks, and `<meta http-equiv="refresh">` each ended on Chromium's error page, and the sink heard nothing.
- **WebRTC is not a policy's to refuse in Chromium.** It doesn't know CSP's `webrtc` directive, and a peer connection the app made sent STUN to the sink over UDP. Removing every `RTC*` constructor before the app's script runs stopped it; a frame the app makes is of another opaque origin, so it can't take them back from one.
- **Everything else failed as designed:** `fetch`, XHR, WebSocket, EventSource, `sendBeacon`, an image, a CSS beacon, prefetch, preconnect and DNS prefetch, `window.open`, a form's submit, the top's or the parent's navigation, service workers, `document.cookie`, `localStorage` and the parent's DOM; and `WebAssembly.compile`, with no `'wasm-unsafe-eval'`, was refused.

## Decision

- **Two frames, on an origin of their own.** The portal frames the sandbox on the apps' origin, `apps.<host>`, with `sandbox="allow-scripts allow-same-origin"`, no `allow`, and no referrer; the sandbox runs the app in a frame of its own with `sandbox="allow-scripts"` alone, an opaque origin, with no forms, popups, top navigation or downloads.
- **`Site(apps=...)`** names the apps' origin: https, or http on loopback, a host with no path, user, query or fragment, kept as its origin. `config.json` carries it as `apps`, null where the deployment runs none. The UIs' policy gains `frame-src` naming it alone, and keeps `frame-ancestors 'none'`.
- **`SandboxOrigin(app, apps=, portal=)`,** an ASGI middleware, answers every request whose `Host` is the apps' origin's, whatever its scheme, since an edge that ends TLS hands https on as http: `GET /` is the sandbox page, anything else 404 and a write 405, a WebSocket closed, and nothing from the application reaches it. It refuses an apps' origin that is the portal's. Every answer carries the sandbox's policy, `nosniff`, no referrer, `X-DNS-Prefetch-Control: off`, a `Permissions-Policy` that allows no powerful feature, and `no-cache`; nothing sets a cookie.
- **One policy, the app's, for both documents:** `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'`, and for the sandbox `frame-ancestors` the portal's origin. `default-src 'none'` refuses every fetch, socket, worker and frame, and so the app's frame navigating; there is no `'wasm-unsafe-eval'` or `'unsafe-eval'`, so no WebAssembly and no `eval`, though portalr's own policy allows first-party WebAssembly ([ADR-0041](0041-first-party-webassembly-in-the-apps-policy.md)). The sandbox's script is inline, not allowed by its hash, since the app inherits the policy and a hash would refuse it; the sandbox puts no untrusted markup in its own page, so that costs nothing. `web/ui/csp/app-policy.txt` holds it, and portalr's and ui's tests hold the server's and the sandbox's copies to it.
- **The app's document begins with the host's:** its own copy of the policy, `x-dns-prefetch-control` off, and a script that removes every `RTC*` constructor, then the app's HTML.
- **The sandbox page is built by app's build,** from `ui/src/sandbox-page.ts`, bundled and minified by Vite into its one inline script (`@portalr/ui/sandbox`), and written to `static/sandbox/index.html` beside the UIs; the wheel check fails without it. It runs only when framed with `?host=` naming the portal's origin, takes the app's HTML from its parent alone, at that origin, and relays: the app's messages to the portal as JSON text, dropped past 64 KB or where JSON can't hold them, and the portal's to the app.
- **The bridge is portalr's, in `ui`'s `app-bridge.ts`,** on MCP Apps' methods (`2026-01-26`): it takes a message only from the sandbox's window and the apps' origin, as JSON text within 64 KB, a JSON-RPC 2.0 request or a notification it knows, and 60 a minute a frame; past them it stops answering, and the chrome says so. It answers `ui/initialize` with the host's context, `tools/call` for `get_state`, `set_state` and `submit` and no other tool, and `ui/open-link`; any other request is "method not found". It hears `ui/notifications/size-changed`, sizing the frame between 120 and 2,000 pixels, and sends `ui/notifications/host-context-changed` when the scheme, colour-blind mode, forced colours or reduced motion change.
- **The host's context** is MCP Apps' `hostContext`: `theme`, and `styles.variables`, portalr's colours resolved to what the browser draws, under portalr's names (`--paper`, `--fg`, `--accent`, `--chart-1` and the rest) and MCP Apps' (`--color-background-primary` and the like), with `locale`, `timeZone`, `platform` and `displayMode`, and portalr's `colourBlind`, `forcedColours` and `reducedMotion`.
- **State is coalesced,** as the RFC words it: a patch applies at once to what the app sees, and is written as the person's edit of `/state`, replaced whole on the version it was read at, at most once every five seconds. A write on a head that moved on waits for the new head, and writes the patches on it again; one refused for another reason puts the state back as the head has it, and the chrome says why: off in the workspace, or the person may not change it.
- **A submission and a link are the person's.** Each is asked in the host's own dialog, outside the frame: a submission shows its values as JSON text, and is sent only once they agree, as a `submission` with `app_id`, the version, a nonce and its derived id; a link shows its full address, opens only if it is http, https or `mailto:`, and in a new tab with no opener or referrer. One question is open at a time; another is declined.
- **The chrome is the host's:** the app's title as a heading; "Made by the agent. Runs sandboxed and can't reach the network." with its version; its summary, its text equivalent; a border round the frame, which the app can't draw over; the frame titled "<title>: an app made by the agent"; and a link to skip past it, which the keyboard reaches first, to a point after it.
- **Nothing runs** where the app is archived ("This app is switched off: it was archived."), where mini apps are off in the workspace (the kit's "Not available in this workspace: mini apps are off."), or where the deployment names no apps' origin, or names the portal's own. The label and the summary are shown instead.
- **The kill switch stops a running app.** The app gives a page's apps an `AppHost`, `useAppHost(config)`, and, while an app's page is open, reads the workspace's integrations again every half minute, so mini apps switched off, by the deployment, the tenant or the workspace, stop it at the next read; a write refused as `not_enabled` reads them at once, as every command's does ([ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md)); archiving stops it as the artifact's event arrives.
- **Running an app is an add-on,** `apps` (`ui/src/on-demand/apps.tsx`, [ADR-0044](0044-highlighting-and-math-on-demand.md)): the frame, the bridge and the dialog load with the first app a page runs, so no page that runs none holds a bridge. Its ceiling is 9 kB, total and largest; it measured 4.9 kB. The chrome is in the app's own bundle, whose total grew from 466.4 kB to 470.5 kB, mostly in the small chunks the add-on now shares with the routes, past the 470 kB ceiling: it is 474 kB, amending [ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md), whose initial and largest are unchanged.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| The sandbox's script | **Inline, under the app's policy (chosen)** | One policy for both documents; the app's scripts run | `'unsafe-inline'` on a page with no untrusted markup |
| | By its hash, as the RFC wrote | The narrowest policy for the sandbox | The app inherits it, and none of its scripts run |
| | A third document, fetched with a policy of its own | Each policy its own | Another page, a loader that writes the app into itself, and a `frame-src` to allow it |
| WebRTC | **Its constructors removed first (chosen)** | Holds in Chromium today | A script of the host's in the app's document |
| | CSP's `webrtc 'block'` | The policy alone | Chromium ignores it |
| Serving the sandbox | **A middleware on the application, by `Host` (chosen)** | The same release's build, one process, and a second port locally | The application answers the apps' origin |
| | The edge serving a file | No application in the path | The edge needs the build, and a policy of its own to keep |
| Running an app | **An add-on (chosen)** | No bridge where no app runs; the app's total grows 4 kB | Small shared chunks |
| | In the app's bundle | No add-on | The total grows 5.4 kB, and every page holds the bridge |

## Consequences

- Easier: an agent's app runs where an operator names an apps' origin and a workspace switches mini apps on, and nowhere else.
- Easier: what the policy can't refuse is written down, with what refuses it instead, and stackr's hostile corpus holds both in Chromium in CI.
- Harder: an app's frame can hold the keyboard, as any page can; the link before it is the way past it, and the label and summary stay its text equivalent.
- Harder: an app whose state two people change at once keeps each person's patches, written again on the other's, never merged.
- Harder: a running app is stopped within half a minute of being switched off, not at once, unless it writes.

## Action items

1. [x] `Site.apps`, `config.json`'s `apps`, `frame-src`, `SandboxOrigin`, the sandbox page and the wheel's check.
2. [x] `ui`'s bridge, sandbox, `AppFrame` and the `apps` add-on; the app's host and kill switch; tests and screenshots.
3. [ ] stackr: the apps' origin at the edge and in the template, locally on its own port, and the hostile corpus in Chromium in CI (lattice RFC-0005, phase 2).
