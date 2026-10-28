# ADR-0010: The LLM gateway

**Status:** Accepted, amended by [ADR-0047](0047-an-upstream-gateway-for-the-model-groups.md) and on 2026-10-27 (below)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

RFC-0001 puts the LiteLLM proxy in front of every model: model aliases in the style already in use (with an OpenRouter wildcard and local servers), model groups with fallbacks, a team per tenant with budgets and rate limits, guardrails selected per request, and telemetry that continues the application's trace. The libraries reach it through pydantic-ai's `LiteLLMProvider` ([artifactr ADR-0031](../../artifactr/adr/0031-litellm-proxy-first.md)); to them it is the LLM gateway port ([ADR-0005](0005-ports-and-adapters-for-the-stack.md)).

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

## Amendment (2026-10-27): `prompt-injection` reads tool results

`prompt-injection` read every message of a request: the system prompt, the person's prompt, the model's replies and the arguments of its tool calls, and tool results. Its categories are word lists; `prompt_injection_jailbreak` blocks at high severity when a word such as "enter" and one such as "unlimited" fall in one sentence, and sentences end only at `.`, `!` or `?`, so a page of markup is a few very long sentences. An agent asked for a landing page wrote one into a mini-app tool's arguments; the tool succeeded, and the next request of the turn, which carried those arguments, was blocked (`conditional match 'enter + unlimited' detected (severity: high)`). Every later request of that thread would have been blocked too, since each carries the thread's history.

The guardrail now has `scan_only_tool_results: true` (LiteLLM v1.103.0, applied to any guardrail from the configuration file): it reads tool-role messages only, and skips the system prompt, the person's prompt, and the model's replies, tool arguments and tool definitions. A request without a tool result isn't scanned. The proxy applies this to every client that asks for `prompt-injection`, not only the libraries.

- **Kept:** injection through what tools bring back: fetched web pages, the contents of files a connector or tool read, another service's answers.
- **Lost:** the word-list check of everything in user and system messages: the person's own prompt, and outside text that arrives there instead of through a tool, such as an email, a document or a web page the person pasted or attached, or that a client puts in a system prompt. That text is as untrusted as a tool result and is no longer scanned. The person is an authenticated user of the tenant, in their own workspace, and the provider's own safety still applies to direct prompts; a word list was a weak defence against a determined person, or a crafted document, anyway.
- **Still possible:** a false positive on a tool result that repeats generated content. artifactr's `read_artifact` returns a mini app's whole HTML, so an agent that reads a generated app back can block its thread one step later, as before ([#830](https://github.com/alexnodeland/lattice/issues/830)).
- **Not chosen:** a higher severity threshold (the match was already `high`); sending the guardrail only on a turn's first request, or when the newest message is the person's (the thread's history still carries the model's tool arguments, so its next turn is blocked too); `skip_tool_message_in_guardrail` (it keeps the model's tool arguments, where the page was); `experimental_use_latest_role_message_only` (read only by the Bedrock and Prisma AIRS guardrails at this version, not by the content filter).
- **Revisit:** choosing the guardrail per tool, so a result from a tool that only echoes what the model made (artifactr's mini-app and artifact tools) isn't scanned while one from an outside source is. The proxy can't tell tools apart in a tool message, so that would be the libraries' `GuardrailPolicy` choosing per request from the newest tool result.
