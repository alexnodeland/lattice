# ADR-0043: The LiteLLM adapter

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0031](0031-litellm-proxy-first.md) routes agents through a LiteLLM proxy, reached with pydantic-ai's `LiteLLMProvider`, and has a `[litellm]` extra add per-request metadata, per-workspace guardrails, typed handling of guardrail blocks and tenant key resolution. [RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) left open the metadata's shape, how keys reach requests, how a block is recognised, and where in pydantic-ai's hooks the handling sits.

LiteLLM reads per-request metadata (tenant, tags, session, trace) from the body's `metadata` and guardrail names from `guardrails`. It answers a request a guardrail blocks with HTTP 400 and an error that mentions the guardrail. pydantic-ai 2.51 surfaces that as `ModelHTTPError`. A streamed request is only sent when its events are first read, so its error reaches the capability's `wrap_run_event_stream`, not `on_model_request_error`.

## Decision

- **The model is the port** ([ADR-0034](0034-ports-and-adapters-for-integrations.md)). `litellm_model(name, api_base=, api_key=)` is pydantic-ai's `OpenAIChatModel` over `LiteLLMProvider`, and `LiteLLMGateway` is a capability, so the rest of artifactr is unchanged. The extra needs pydantic-ai's `openai` dependency, not the litellm package.
- **Each request carries**, through the model settings' `extra_body` and `extra_headers`, added in `before_model_request`:
  - `metadata`: the tenant, workspace, thread and run; the thread as `session_id`; the person as `trace_user_id`; the current trace as `existing_trace_id`, so LiteLLM's own Langfuse logging joins the turn's trace; and `tags` (`artifactr`, `tenant:…`, `workspace:…`, and the application's)
  - `guardrails`: the names the application's `GuardrailPolicy(tenant, workspace)` returns
  - the W3C trace context (`traceparent`, and the turn's `session.id` as baggage), for LiteLLM's OpenTelemetry integration
  - `Authorization: Bearer <key>`, from the application's `TenantKey(tenant)`, a callback onto its secret store; without a key, the model's own is used
- **Keys never reach the log or spans.** pydantic-ai records no request headers on spans; artifactr records none anywhere.
- **A guardrail block is an HTTP 400 whose error mentions a guardrail.** It becomes `GuardrailBlocked`, a `RunFailure` with the reason `guardrail_blocked` ([ADR-0042](0042-typed-run-failures.md)), raised from `wrap_run_event_stream` for streamed runs and `on_model_request_error` otherwise. Its message names the guardrail and never repeats what was blocked. It is not retried: the OpenAI client does not retry 400s, and the gateway raises rather than asking the model to try again.

## Options considered

| Option | Library dependency | Typed guardrail outcome |
|---|---|---|
| **pydantic-ai's LiteLLM provider and a capability (chosen)** | None beyond pydantic-ai | Yes |
| The litellm package's `Router` in process | litellm | Only through its exceptions |
| A custom HTTP client that adds headers | None | No: the capability cannot see the session |

## Consequences

- Easier: spend, rate limits and guardrail hits break down by tenant and workspace in LiteLLM, and its logs join the turn's trace.
- Harder: recognising a block depends on LiteLLM's error text mentioning the guardrail; a test pins the shape.

## Amendment (2026-09-29): `litellm_model` takes model settings

`litellm_model` took no model settings, so an application that wanted a temperature, or a reply the proxy mocks for a smoke test, had to set them on every agent with `Agent(model_settings=...)`. stackr's application template found it ([#51](https://github.com/alexnodeland/artifactr/issues/51)).

- **`litellm_model(name, api_base=, api_key=, http_client=, settings=)`** passes `settings` to `OpenAIChatModel` as the model's defaults, as every pydantic-ai model takes them. pydantic-ai merges the model's, the agent's and the run's settings key by key, the run's winning, before `LiteLLMGateway` adds its metadata to the request's `extra_body`, so a model's `extra_body={"mock_response": ...}` reaches the proxy beside the gateway's metadata.
- reflexr's `litellm_model` takes the same `settings`, with the same meaning (reflexr's ADR-0022, amended the same day).

## Action items

1. [x] `litellm_model`, `LiteLLMGateway`, `GuardrailBlocked`, tested against a fake proxy.
