# ADR-0033: Egress pinned by an ORIGINAL_DST cluster that the authorizer addresses

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Amends:** [lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md), "Egress: one policy and one proxy" and Decision O9's two conditions, now verified

## Context

[lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md) makes Envoy the egress proxy (Decision O9) on two conditions:

- a purpose that carries credentials is called as a plain-HTTP forward-proxy request, so Envoy originates TLS and can inject them;
- pinning the checked address against DNS rebinding is verified in M2, with smokescreen behind Envoy as the fallback if it can't be.

Its Unverified list adds two more claims: that Envoy can be made to connect only to the address the authorizer resolved and checked, and that `ext_authz`'s allow response sets upstream headers and its dynamic metadata reaches the access log.

The spike for [#943](https://github.com/alexnodeland/lattice/issues/943) tested them with Envoy 1.40.2, on 2026-10-31 ([its write-up](https://github.com/alexnodeland/lattice/blob/main/spikes/0943-egress-vault/README.md), [#1242](https://github.com/alexnodeland/lattice/pull/1242)). A DNS server flipped each name's answer per query, from an allowed address to `127.0.0.1`, and the authorizer always resolved first. The spike found:

- **The dynamic forward proxy rebinds.** With `ext_authz` before it, the authorizer checked the allowed address, and Envoy then resolved the name again and connected to `127.0.0.1`, five times in five.
- **A cluster addressed by the authorizer's answer doesn't.** With an `ORIGINAL_DST` cluster reading the address from a header the authorizer sets, Envoy never resolved the name, and connected only to the address the authorizer had checked, five times in five. A caller's own value for that header was overwritten by the authorizer's.
- **The routing header can't be stripped on the route.** A route's `request_headers_to_remove` runs before `ORIGINAL_DST` picks the host, which then finds no header and answers 503 (`No downstream connection or no original_dst`). The cluster's upstream HTTP filters run after the host is chosen, and stripped it there without harm.
- **The HTTP `ext_authz` service can't check CONNECT.** Envoy sends a CONNECT's check to the authorizer as a CONNECT, which its own async client fails with 503. The filter then fails closed (`ext_authz_error`, 403), even when the authorizer allows. With the gRPC service and the same cluster, CONNECT tunnels were checked and pinned.
- **Injection works where Envoy originates TLS.** The allow response set `Authorization` on a plain-HTTP forward-proxy request sent upstream over TLS (`auto_sni`, `auto_san_validation`). The caller's `Authorization`, `x-api-key`, `Proxy-Authorization` and `X-Lattice-Secret` were removed, and nothing of the credential came back to the caller. A certificate whose SAN didn't match was refused (503).
- **Metadata reaches the access log.** Headers the authorizer returned under `x-lattice-*` were lifted into `ext_authz`'s dynamic metadata, and Envoy's JSON access log wrote tenant, workspace, purpose and the checked address.
- **The authorizer down refuses everything.** With `failure_mode_allow: false` and the authorizer stopped, every listener answered 403.
- **smokescreen** resolves once and dials the address it checked, so it refused the same rebinding (407). It has no published image. It isn't needed.

## Decision

- **Envoy connects to the address the authorizer checked, and to nothing it resolved itself.** Each egress route's cluster is `ORIGINAL_DST`, with `original_dst_lb_config: {use_http_header: true, http_header_name: x-lattice-upstream}`.
  - The authorizer resolves the destination, checks every address it got against `lattice_core.egress`'s refused ranges and the purpose's internal destinations (Decision O10), and on allow answers `x-lattice-upstream: <checked address>:<port>`.
  - Envoy's dynamic forward proxy is not used for egress, since it resolves again between the check and the connection.
  - The internal destinations' static clusters (RFC-0011) may be replaced by this cluster, since the authorizer already checks the address against the declared range. That is for phase 4 to settle.
- **Only the authorizer sets the routing header.** `lattice_core.egress.envoy` renders:
  - a `header_mutation` filter first in each listener's chain, removing any `x-lattice-upstream*` the caller sent, so a header missing from an allow response leaves the cluster nothing to connect to (503);
  - a `header_mutation` filter in the cluster's upstream HTTP filters, before `upstream_codec`, removing it before the request leaves. Never a route's `request_headers_to_remove`, which empties the header before the cluster reads it.
  - The first of these wasn't in the spike, which showed the caller's value overwritten only when the authorizer sets its own.
- **The authorizer speaks gRPC `ext_authz`** (`envoy.service.auth.v3.Authorization`), for every listener, so that CONNECT, the mode a credential-free purpose such as a package registry may use, is checked like everything else. `lattice_core.egress`'s authorizer is served over gRPC behind its extra. RFC-0011's FastAPI router is not how Envoy reaches it, though the application may still mount one for its own callers.
- **A purpose that carries credentials is called as a plain-HTTP forward-proxy request, and Envoy originates TLS** with `auto_sni` and `auto_san_validation` against the deployment's trust store.
  - The allow response sets the header the purpose names, overwriting the caller's, and removes `Proxy-Authorization`, `X-Lattice-Secret`, `x-api-key`, the forge's header and, when nothing replaces it, `Authorization`.
  - The router has `suppress_envoy_headers: true`.
- **The access log is Envoy's JSON log, with the authorizer's answer as dynamic metadata:** listener, method, authority, response code and flags, upstream host, the checked address, tenant, workspace, purpose, caller, bytes and duration. Never bodies, headers or credentials.
- **The authorizer down means everything refused:** `failure_mode_allow: false`, and a timeout per check.
- **smokescreen is not part of the stack.** O9's fallback is not needed.

## Options considered

| Option | For | Against |
|---|---|---|
| **`ORIGINAL_DST` addressed by the authorizer (chosen)** | Envoy never resolves, so there is nothing to rebind; one cluster for every destination; fails closed without the header | The routing header must be stripped twice, at the right points |
| Dynamic forward proxy, as RFC-0011 sketched | Envoy's own DNS cache and its stats | Rebound to `127.0.0.1` every time in the spike |
| Dynamic forward proxy fed the checked IP through `set_filter_state` | Also held in the spike | A DNS cache that only ever holds IP literals: more parts for the same result |
| smokescreen behind Envoy | Resolved-address checks built in | A second proxy in series; taint still unexpressed; no published image; not needed |
| An HTTP `ext_authz` service (RFC-0011's FastAPI router) | Simplest to mount in the application | Can't check a CONNECT |

## Consequences

- Easier: the SSRF suite has one place to test, the authorizer's check. Envoy holds no DNS answer an attacker can change.
- Easier: one cluster shape for public and internal destinations alike.
- Harder: the authorizer is a gRPC service, so `lattice_core.egress`'s extra brings `grpcio` and Envoy's `ext_authz` messages, and its tests need a gRPC client.
- Harder: the authorizer must check every address a name resolves to, and choose the one it answers. The spike took the first A record only, so IPv6 and mixed answers are still to test.
- To revisit: redirects, which Envoy passes back to the caller and which are checked again as new requests; file-based xDS reloads; taint narrowing. The spike exercised none of them.

## Action items

1. [ ] `lattice_core.egress.envoy` renders `ORIGINAL_DST` clusters, both header strips, gRPC `ext_authz` with `failure_mode_allow: false`, TLS origination for credential purposes and the JSON access log (RFC-0011 phase 4).
2. [ ] `lattice_core.egress`'s authorizer, over gRPC: resolve, check every answer, answer `x-lattice-upstream`, inject, return the metadata.
3. [ ] The SSRF suite at Envoy includes the spike's rebinding test, a caller-sent `x-lattice-upstream`, an allow response without it, and CONNECT.
