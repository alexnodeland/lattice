# ADR-0004: Native views of a tenant's observability

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision P4 of [lattice RFC-0002][rfc-0002], portalr, the portal.

## Context

The stack's tools, Langfuse, Tempo, Loki, Prometheus and LiteLLM, are shared by every tenant, and none of their UIs is tenant-scoped. A tenant's admins still need to see what their users thought of the agent, how its evaluations trend, what it costs, and why a run failed. Rebuilding Grafana's dashboards or Langfuse's analysis tools inside portalr would be a large, moving target.

## Decision

- **The admin UI shows a tenant its own** feedback, evaluations, usage and spend, traces and sessions, and logs, natively, from what portalr's readers return for that tenant.
- **Operators get deep links out** into Langfuse and Grafana, for any run, session or tenant. portalr doesn't rebuild those tools' dashboards or analysis.
- **The views use open-source components portalr vendors and owns:** AgentPrism for traces, ported to Tailwind 4 and Base UI; Tremor's copied components on Recharts, and uPlot, for charts; and a virtualized list of its own for logs.

## Options considered

| Option | For | Against |
|---|---|---|
| **Native views of a tenant's own data, and deep links for operators (chosen)** | Tenant admins see their own data without access to shared tools. Operators keep the tools' full power | Each native view needs its tool's API, which changes on the tool's schedule |
| Everything native, dashboards included | One UI for everyone | Rebuilds Grafana and Langfuse, and never catches up |
| Links only | Least to build | Tenant admins can't use the links: none of the tools is tenant-scoped |

## Consequences

- Easier: a tenant admin answers "why did this run fail" and "what did this cost" without an operator.
- Harder: each reader is small and optional, but there are five, and each breaks when its tool's API changes; its card's status shows when it does.
- Harder: AgentPrism is alpha, and vendoring it means owning its port.

[rfc-0002]: ../../rfcs/0002-portalr-the-portal.md#decisions
