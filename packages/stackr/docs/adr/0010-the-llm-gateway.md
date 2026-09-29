# ADR-0010: The LLM gateway

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 puts the LiteLLM proxy in front of every model: model aliases in the style already in use (with an OpenRouter wildcard and local servers), model groups with fallbacks, a team per tenant with budgets and rate limits, guardrails selected per request, and telemetry that continues the application's trace. The libraries reach it through pydantic-ai's `LiteLLMProvider` ([artifactr ADR-0031](https://github.com/alexnodeland/artifactr/blob/main/docs/adr/0031-litellm-proxy-first.md)); to them it is the LLM gateway port ([ADR-0005](0005-ports-and-adapters-for-the-stack.md)).

Checking LiteLLM 1.103.0, the current release, against its source settled what the RFC left open:

- **Licensing.** Teams, virtual keys, budgets and rate limits are open source. Guardrails attached to a team or key, and guardrails with per-request parameters, need an Enterprise licence. The built-in content filter (regular-expression PII masking and prompt-injection categories), Presidio and several hosted checks are open source; `hide-secrets` is licensed code.
- **Failure modes.** The proxy has no configuration validator. It starts without a guardrail it can't load, logging an error, and ignores unknown keys in most sections.
- **Telemetry.** Its OpenTelemetry integration continues an incoming `traceparent`. Version 2 of that integration makes the proxy's FastAPI server span the root, with GenAI attributes, and leaves prompts and responses out unless asked. It also records token usage, cost and duration metrics, labelled with per-key identifiers unless those are excluded.
- **Tenancy.** A team alias isn't unique, but a team id is.
- **Testing.** A key can send a mocked response only if its team allows it, and a mocked call is routed, filtered, priced, charged and traced like a real one.

## Decision

- **The LiteLLM proxy, pinned to a release, configured in `deploy/litellm/config.yaml`,** published on port 4400 (LiteLLM's default, 4000, is commonly taken).
- **Models:**
  - aliases for Anthropic, OpenAI and Gemini models
  - an `openrouter/*` wildcard
  - LM Studio and an `omlx/*` wildcard, on the host through `host.docker.internal`
  - the model groups `default` and `fast`, each falling back across providers in `router_settings.fallbacks`

  Applications name groups or aliases, never providers.
- **A team per tenant,** with the id `tenant-<name>`, a budget per period, and optional rate limits and model list, created by `scripts/create-tenant` (`make tenant NAME=...`). It is idempotent: the team is looked up by id, and a key is created only for a new key alias, since a key's secret can't be read back. Applications use a team's keys; the master key only administers the proxy.
- **Two guardrails, open source and in process:** `pii-mask` (masks email addresses, phone and social security numbers, card numbers and cloud and GitHub credentials) and `prompt-injection` (blocks jailbreak, system-prompt and data-exfiltration attempts), both from LiteLLM's content filter. They are off by default and chosen per request with `"guardrails": [...]`, which is how the libraries' `[litellm]` extras apply a workspace's or rule's policy. A blocked request is an HTTP 400 naming the guardrail. Presidio needs two more services and stays an option; licensed guardrails are not used.
- **Guarding against silent failure:** `make validate` checks the configuration statically (model groups that fallbacks name, open guardrail integrations and modes, every `os.environ/` reference set in `compose.yaml`, no keys in the file), and the smoke test checks that the running proxy loaded every guardrail and model group.
- **Telemetry:** version 2 of the OpenTelemetry integration, sending traces and metrics to the Collector over OTLP HTTP, only when the `observability` profile runs. The metrics keep model, provider and team (the tenant), and exclude per-key and per-deployment identifiers, as the libraries' cardinality policy does.
- **State:** its database `litellm` on the database adapter, created by `db-init` ([ADR-0008](0008-langfuse-and-its-services.md)); routing state and a 10-minute response cache in database 1 of the shared Valkey. The master key and the salt key that encrypts stored credentials are generated into `.env`; the salt key never changes.
- **Offline and predictable:** the proxy uses the model prices bundled with its release, and reads no `.env` of its own.
- **The smoke test** creates a key on a `stackr-smoke` team that alone allows mocked responses, and checks routing, both guardrails, price, recorded spend, and the trace continuing through the proxy, with no provider key.

## Options considered

### Guardrails

| Option | Licence | Extra services | Per tenant |
|---|---|---|---|
| **LiteLLM's content filter, chosen per request (chosen)** | Open source | None | Per request, by the libraries' policy |
| Presidio | Open source | Analyzer and anonymizer | Per request |
| Guardrails attached to teams or keys | Enterprise | Depends | Per team |
| Hosted checks (Lakera, OpenAI moderation) | Open source integration | A third-party API | Per request |

### Telemetry integration

| Option | Continues `traceparent` | Prompts on spans | Root span |
|---|---|---|---|
| **Version 2 (chosen)** | Yes | Off unless asked | The proxy's HTTP server span |
| Version 1 (the default) | Yes | On unless turned off | A span of LiteLLM's own |

## Consequences

- Easier: routing, fallbacks and guardrails change in one file, for every application and library.
- Easier: a request's trace runs from the application through the proxy to the provider call, in Tempo and in Langfuse, and spend breaks down by tenant.
- Harder: guardrails are chosen per request, so an application that forgets to ask gets none. The libraries' policies are where the defaults live.
- Harder: Langfuse lists the proxy's Redis and PostgreSQL spans as generations, because they carry `gen_ai.request.model`; they carry no usage or cost, so totals are right.
- Revisit: team-level guardrails if an Enterprise licence is ever in place, and Presidio if regular expressions miss too much.

## Action items

1. [x] The `gateway` profile, `scripts/create-tenant`, the guardrails and telemetry (RFC-0001 phase 4).
2. [ ] Dashboards for the gateway's usage and cost, beside the libraries' own.
