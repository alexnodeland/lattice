# ADR-0036: Egress decided by one pure function: hosts the operator's, and internal destinations declared per purpose

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Records:** [lattice RFC-0011](../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s Decisions O6 and O10, as the egress contract `lattice_core.egress` declares them, beside [ADR-0033](0033-egress-pinned-by-an-original-dst-cluster-that-the-authorizer-addresses.md)

## Context

Everything in v0.3 that calls out (sandboxes, the reader, connectors, MCP servers, coding agents, LiteLLM) would otherwise carry its own allowlist and its own SSRF guard ([#943](https://github.com/alexnodeland/lattice/issues/943)). RFC-0011 puts one policy in lattice-core, which Envoy's authorizer and the in-process guards (the reader's, the sandbox's) all run, so they decide the same way. ADR-0033 settled how Envoy connects only to the address the policy checked. Two of the owner's decisions shape the policy itself: whose hosts these are (O6, 2026-10-30), and how a call reaches a private address at all, such as a self-hosted Forgejo or the stack's own LiteLLM (O10, 2026-10-31).

## Decision

- **One pure function, `decide(destination, purpose, allowed, taint)`,** in `lattice_core.egress`, `CONTRACT` 1.0.0, with its JSON Schema at `packages/lattice-core/schemas/egress.v1.json`. It takes a destination already resolved, every address of it, and answers a `Verdict`: allowed, with the one checked address to connect to, or refused, with the reason. It does no I/O, so the proxy's authorizer and each guard call the same code, and it is tested without a network.
- **Metadata endpoints are always refused,** by name (`METADATA_HOSTS`) or address (`METADATA_NETWORKS`: 169.254.169.254, ECS's 169.254.170.2, Alibaba's 100.100.100.200, and fd00:ec2::254), whatever the purpose and even among public addresses. No internal destination may name one, or declare a range that holds one.
- **Hosts are the operator's alone in 0.3.0 (O6).** A `Purpose` holds the operator's universe of host patterns for it, names or `*.` and a name. A tenant's or workspace's `egress:<purpose>` setting only narrows it, and `decide` takes the narrowed patterns as `allowed`, checking the host against both. No tenant adds a host, not even through a connection's declared hosts, which the connector RFC revisits.
- **Internal destinations are declared per purpose, by the operator alone (O10).** An `InternalUpstream` is an exact host and port with the private range it must resolve into. A call reaches it only under its purpose, on its port, and only when every address resolves inside the range, so a rebinding to another private address is refused. Taint still narrows it. Neither tenant nor workspace narrowing applies to an internal destination, since it isn't one of the purpose's hosts.
- **Every other host resolves to public addresses only.** Each resolved address is checked against `REFUSED`, the private, loopback, link-local, CGNAT and tailnet ranges and the rest that the RFC names. Tunnels to IPv4 (IPv4-mapped, NAT64, 6to4, Teredo) are refused too, as is any address Python's `ipaddress` doesn't call global and any multicast. One address refused refuses the call.
- **A tainted caller is narrowed.** It reaches only hosts in its taint's `seen_hosts`, compared in lowercase without a trailing dot, and never with a URL the caller marks as built from private data.
- **The verdict pins the address.** An allowed verdict carries the first resolved address, every address having been checked, and the proxy connects to it alone (ADR-0033's `x-lattice-upstream`).

## Options considered

| Option | For | Against |
|---|---|---|
| **One pure function in lattice-core (chosen)** | The proxy and each guard decide alike; tested without a network | Every caller resolves first and passes the addresses |
| The policy in Envoy's configuration alone | Nothing to call | Taint and tenants' narrowing change during a run, which static configuration can't follow |
| **Hosts the operator's, narrowed below (O6, chosen)** | No tenant opens a path out on its own | A tenant waits for the operator to add a host |
| Tenants adding hosts through a connection | Self-service | A connection could open any host |
| **Internal destinations per purpose (O10, chosen)** | A self-hosted forge and the stack's services work, each only where declared | One more thing in the operator's configuration |
| Private ranges refused whatever the purpose | Simplest | Blocks a self-hosted Forgejo and the stack's own LiteLLM |
| A path past the proxy for internal services | No declaration | Unpoliced, and unaudited |

## Consequences

- Easier: the reader, the sandbox's proxy and Envoy's authorizer share one tested policy.
- Easier: a self-hosted forge is reached under its purpose and nowhere else.
- Harder: a caller must resolve the host and pass every address; `decide` never resolves it itself.
- Harder: some public-looking addresses are refused, such as IPv4-mapped and NAT64 ones, which a resolver for a public host shouldn't return.
- Follow-ups, in RFC-0011's phase 4: limits per purpose as settings; Envoy's rendered configuration (`envoy(policy)`); the gRPC authorizer that runs `decide`, injects credentials through `Secrets`, and logs each verdict; the reader and the sandbox's proxy as its clients.
