# ADR-0084: Several portal origins: an allow-list, aliases, and a union policy

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland
**Amends:** [ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md) (one portal origin frames the sandbox), [ADR-0055](0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md) (the editors' origins in `frame-src`), native files [ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md) and [ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md) (the shim answers one portal)

## Context

A generated application runs on one machine, and is reached at more than one address: its loopback address on the laptop, `http://127.0.0.1:8800`, and its tailnet name on the owner's phone, `https://<machine>.<tailnet>.ts.net`, where `tailscale serve` forwards 443 to the application ([stackr's template guide](../../stackr/guides/template.md#on-your-tailnet)). A browser compares origins by scheme, host and port, so those are two portal origins. Everything the portal frames was built for one:

- `Site.apps` names one apps' origin, `PORTAL_APPS_URL=http://127.0.0.1:8801`, which the phone can't reach; and `SandboxOrigin` answers `frame-ancestors http://127.0.0.1:8800`, one portal, so a sandbox the phone could reach would still refuse to be framed from the tailnet name ([ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)).
- Each editor's shim is told one portal origin, which it alone hears and answers, and the editor's and the shim's `frame-ancestors` name it alone ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)); the template hard-codes `http://127.0.0.1:<port>/` for each editor.
- The UIs read `config.json`'s `apps` and `editors` wherever they are opened, so from the phone a mini app's frame points at an address that doesn't answer, and shows nothing: a blank frame, with no word why.

The origins themselves were checked loosely: a regular expression in the shim that took any `http://host`, and `Site`'s own checks, which kept an origin as it was spelled.

The owner decided (2026-10-27): proper support for several origins, not a hack; the alias map may be public in `config.json`; `make tailnet` writes one `.env` key; `AUTH_SITE_URL` and email links are left alone; and this holds the v0.2 release. Rejected in design: computing the apps' origin in the browser from `location` (`${protocol}//${hostname}:8801`), which trusts whatever address the page is at and names no allow-list; and deriving each answer's policy from the request's `Host`, which makes the policy depend on the proxy and on a header the browser sends, per request.

## Decision

- **One origin, checked as a browser compares it, in lattice-core.** `lattice_core.origins.web_origin(url, what=)` keeps an origin as `scheme://host[:port]`, lower-cased, the scheme's default port left out, a bracketed IPv6 host as given; it refuses a path, query or fragment, a user or password, a `*` or a `%`, an IP address that isn't loopback, and plain http anywhere but `localhost`, `127.0.0.1` and `::1`. `web_origins(one_or_several, what=)` takes a string or a sequence, each once, in order; `origins(csv, what=, canonical=, limit=8)` reads a comma-separated setting, leaves out repeats and the canonical origin, and refuses more than eight. The shim's regular expression and `Site`'s `_web` are replaced by it, so every origin the portal, the sandbox and the editors are told is held to the same rule. A mixed-case origin is now served in lower case, as `location.origin` spells it.
- **The portal stays canonical; each other origin is an alias with a place beside it.** `Site.origin` is the portal's own origin, where the application names it, and `Site.aliases` is each other portal origin, keyed as a browser compares it, to a `Place`: the apps' origin and the editors for a portal there, held to the same checks as the canonical ones, each place's editors apart from its apps' origin and Supabase's. `beside(portal, extra, apps=, editors=)` derives a place by the port-sibling rule: the application serves the portal, the sandbox and each editor on ports of its own on one machine, and another address that reaches the machine, such as a tailnet name forwarding each port, reaches each on the same port, so the apps' origin beside `extra` is `extra`'s scheme and host on the canonical apps origin's port, and each editor likewise, its path kept. It refuses an `extra` that is the portal itself, and a canonical apps origin or editor with no explicit port, as one at an edge on 443 hasn't: that deployment names its places itself. `config.json` carries `origin` and `aliases`; both are public, as the policy that names them already is.
- **Every policy is a union over the configured origins, each once, in order, never a wildcard.** The portal's `frame-src` names the apps' and editors' origins of the canonical place and of every alias (`ui.policy`); the sandbox's `frame-ancestors` names every portal origin (`sandbox_policy`); the editor's `frame-ancestors 'self' <portals>` and the shim's `frame-ancestors <portals>` likewise (`editor_policy`, `shim_policy`). `SandboxOrigin(app, apps=, portal=)`, `sandbox_policy`, `editor_policy`, `editor_app`, `shim_page` and `shim_policy` take a string or a sequence: a string is served as before, byte for byte, but for the shim's script. `SandboxOrigin` answers every apps' origin's host alike, serves `GET /` and `HEAD /` alone, 404 for any other path and 1008 for a WebSocket, and refuses any apps' origin that is any portal's.
- **The shim learns which portal frames it at runtime.** `shim_page` writes every portal origin into `data-portals`; the portal's frame adds `?host=<location.origin>` to the shim's URL; the shim takes `?host=` only if it is among them, and with one portal needs none; with several and no valid `?host=` it does nothing: no listener, no message, and the build isn't loaded. The chosen portal is the only origin the shim posts to and hears from, as before. Its script's hash, in its policy, follows the script. `ui`'s CSP tests run the script as artifactr writes it (`csp/shim-script.js`, held to the source by a portalr test).
- **The UIs resolve their place from the address they are at,** `deploymentAt(config, location.origin)`: the alias's place at an alias, the canonical place at the canonical origin or where no origin is named (every deployment from before this record), and nothing anywhere else. The app's host, `CheckOut`'s editor and a thread's inline file use it. At an address the deployment names no place for, the app's label says so in words, "Apps don't run at this address: open the portal at <canonical> or <alias>", never a blank frame; a file there is read and downloaded, and its editor isn't opened in place.
- **Cookies: none, ever, on these hosts.** On loopback and on a tailnet the portal, the sandbox and each editor share a host and differ by port alone. Cookies are host-scoped, not port-scoped, and `SameSite` ignores the port, so a cookie any of them set would reach the others; `__Host-` doesn't help across ports. None sets one today, and tests on the portal's, the sandbox's and the editor's answers assert no `Set-Cookie`, with the reason beside them: a future cookie must not be introduced on any of these origins. The portal's session stays in `localStorage`, per origin: a phone signs in on the tailnet address once, apart from the laptop's.
- **Each extra origin is trusted as the portal is:** it may frame the sandbox and the editors and drive their bridges. Only origins the operator controls go in the list, which is why the rule is strict and the list short.
- **Held in Chromium** by `ui`'s CSP tests (`csp/origins.test.ts`): the harness page reached at `127.0.0.1` and at `localhost`, two origins, each runs a mini app in the sandbox beside it (`http://localhost:<apps port>` beside `http://localhost:<page port>`) and hears the shim's `ready` from the editor beside it; a third origin that frames the sandbox or the shim is refused by their `frame-ancestors`, and hears nothing; the sandbox and the shim answer only the portal origin their frame names, which must be the page's own, so a page at one portal origin can't speak as another; and a shim framed with no `?host=`, or one it wasn't told, loads nothing.

Built here (lattice-core, artifactr, portalr). Planned, in the next change: stackr's template reads `PORTAL_EXTRA_URLS` (a comma-separated list, through `origins(..., canonical=PORTAL_URL)`), passes `origin=`, `aliases={extra: beside(...)}` to `Site`, every apps' and portal origin to `SandboxOrigin`, and every portal origin to each editor's `editor_app`; and `make tailnet` forwards the apps' and editors' ports beside 443 and writes that one key.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where the second origin's place is known | **An allow-list in settings, aliased in `config.json` (chosen)** | Explicit, checked at startup, one policy per deployment | A key to set; the map is public |
| | Computed in the browser from `location` | Nothing to configure | Trusts any address the page is at; the policy can't name it |
| | Derived per request from `Host` | Nothing to configure | A policy per request, proxy-dependent; the shim and sandbox still need the list |
| The sandbox and the shim, told several portals | **Every portal in `frame-ancestors`, and `?host=` picks one (chosen)** | One page, one policy; the message target stays one origin | The frame must say who it is, and a shim told several is inert without it |
| | One sandbox and shim per portal origin | Nothing at runtime | A port per origin per editor; the same page served many times |
| Where the resolver lives | **The app, `deploymentAt` (chosen)** | Tiny; the only reader of `apps` and `editors` | The kit's `AppHost` gains one optional field for the reason |
| An unknown address | **Say where to open the portal (chosen)** | No silent blank frame; the reason is actionable | The alias map is public |
| | A blank frame, as before | Nothing to show | The reader can't tell why |

## Trade-off analysis

An allow-list costs one setting and keeps every policy static and explicit, which is what a Content-Security-Policy is for; computing origins in the browser or per request would make the policy follow the request, which the design rejected. The union keeps the single-origin deployment exactly as it was: a string is served byte for byte, and the extra origins are added, never substituted. The shim's `?host=` is the one runtime choice, and it is bounded by the list the shim was told and by `frame-ancestors`, so a page not in the list can neither frame the shim nor make it speak.

## Consequences

- Easier: a deployment reached at two addresses runs mini apps and opens editors in place from both, once the template names them (planned).
- Easier: every origin the portal is told is checked the same way, in one place, and a mistake fails the start with its reason.
- Harder: plain http is refused off loopback, where the shim's regular expression took it; a deployment that named a LAN address over plain http must use https or a loopback address. The owner's local stacks bind loopback by default.
- Harder: an origin is served in lower case with its default port left out; a deployment that spelled one otherwise sees the policy change, with the same meaning to a browser.
- Harder: the shim's script changed, so its hash in its policy did; its page is no longer byte for byte what it was.
- Deferred: the template and `make tailnet`; a `Host` allow-list on the application against DNS rebinding on loopback; a custom domain beside a tailnet, which needs the places named explicitly, since `beside` derives none for an edge on the default port.
- Budget: no size budget's ceiling moved for the resolver and the reason.

## Action items

1. [x] `lattice_core.origins`; the shim, the editor and the sandbox on one origin or several; `Site.origin`, `Site.aliases`, `Place`, `beside`; `config.json`; the union policy.
2. [x] `deploymentAt`, `?host=` on the shim's URL, the reason at an unknown address; the CSP harness at two origins.
3. [ ] stackr's template and `make tailnet` ([stackr ADR-0042](../../stackr/adr/0042-a-generated-application-as-a-local-product.md), [ADR-0043](../../stackr/adr/0043-native-files-in-the-template.md) and [ADR-0053](../../stackr/adr/0053-run-everything-together.md) to amend).
