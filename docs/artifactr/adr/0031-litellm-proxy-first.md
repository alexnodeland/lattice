# ADR-0031: LiteLLM, proxy first, for routing and guardrails

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

Applications need to route agents across models and providers (model groups, fallbacks, load balancing), control spend per tenant, and apply guardrails (PII masking, prompt-injection and content checks) consistently. LiteLLM provides all of this as a proxy with an OpenAI-compatible API, or in process as the litellm package's `Router`. pydantic-ai 2.51 has a native `LiteLLMProvider`, and its model settings carry `extra_body` and `extra_headers` per request, which is how LiteLLM receives metadata, tags and guardrails.

## Decision

- **Proxy first.** The LiteLLM proxy runs in stackr and owns routing, budgets, rate limits and guardrails. artifactr reaches it through pydantic-ai's `LiteLLMProvider` and does not depend on the litellm package.
- **A `[litellm]` extra** provides `litellm_model(...)`, per-request metadata (tenant, workspace, thread, run, session, trace id) added by the capability, guardrail policies per workspace, and typed handling of guardrail blocks.
- **Each tenant is a LiteLLM team**, with virtual keys, budgets and rate limits. The application supplies the key for a tenant through a callback. Keys never appear in the log or on spans.

## Options considered

| Option | Library dependencies | Where routing lives | Per-tenant budgets |
|---|---|---|---|
| **Proxy first (chosen)** | None beyond pydantic-ai | The proxy's configuration, in stackr | Teams and virtual keys |
| In-process `Router` | The litellm package | Application code | Application code |
| Both, pluggable | Optional litellm | Either | Either |

## Consequences

- Easier: routing, fallbacks and guardrails change in configuration, without code changes, and apply to every library and application the same way.
- Easier: spend and guardrail hits break down by tenant, workspace and thread in LiteLLM, Langfuse and Grafana.
- Harder: a proxy to run; stackr provides it.

## Action items

1. [ ] Implement RFC-0002 phase A7, and the proxy in stackr.
