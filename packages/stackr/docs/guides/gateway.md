# The LLM gateway

The `gateway` profile runs the LiteLLM proxy: an OpenAI-compatible API in front of the model providers and local model servers. It is the LLM gateway port, so applications name a model group and send a tenant's key, and routing, fallbacks, budgets and guardrails are the gateway's configuration, never an application's ([ADR-0010](../adr/0010-the-llm-gateway.md)).

| | Address |
|---|---|
| The API, on this machine | <http://localhost:4400> (`LITELLM_PORT`) |
| The API, on the `stackr` network | `http://litellm:4000` |
| The admin UI | <http://localhost:4400/ui>, as `admin` with `LITELLM_MASTER_KEY` |

The configuration is `deploy/litellm/config.yaml`; [LiteLLM configuration](../reference/litellm.md) lists every model, fallback, guardrail and setting in it.

## Models

Applications ask for a **model group** or an **alias**, never a provider's model:

| Name | What it is |
|---|---|
| `default` | The group agents use: Claude Sonnet, falling back to `gpt-4o`, then `gemini-2.5-pro` |
| `fast` | A cheaper group: Claude Haiku, falling back to `gpt-4o-mini`, then `gemini-2.5-flash` |
| `claude-sonnet`, `claude-opus`, `claude-haiku` | Anthropic's models |
| `gpt-4o`, `gpt-4o-mini` | OpenAI's |
| `gemini-2.5-pro`, `gemini-2.5-flash` | Google's |
| `openrouter/<vendor>/<model>` | Any model on OpenRouter |
| `lmstudio`, `omlx/<model>` | LM Studio and oMLX, on this machine |

A group can hold several deployments, which the router balances (`simple-shuffle`). A failed request is retried twice, a deployment that fails three times is cooled down for 30 seconds, and a group that still fails falls back to the next group in its list. Changing what `default` means is a change to `config.yaml`, for every application at once.

### Provider keys

Put the keys of the providers you use in stackr's `.env`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`. A model whose key is empty fails, and the router falls back; the others still work. After changing a key, run `make up` again: Compose recreates the proxy with its new environment, which `docker compose restart` would not.

### Local model servers

The proxy reaches servers on this machine through `host.docker.internal`, which Compose maps to the host on every platform:

| Model name | Setting | Default |
|---|---|---|
| `lmstudio` | `LM_STUDIO_API_BASE` | `http://host.docker.internal:1234/v1`, LM Studio's server |
| `omlx/<model>` | `OMLX_API_BASE` | `http://host.docker.internal:4243/v1`, oMLX's OpenAI-compatible server |

## Tenants

Each tenant of an application is a LiteLLM **team**, with its own budget and rate limits. Applications call the gateway with one of the team's keys, so its requests are charged to the tenant; the master key only administers the proxy.

```bash
make tenant NAME=acme
make tenant NAME=acme TENANT_FLAGS="--max-budget 20 --rpm-limit 60 --key-alias acme-batch"
```

`make tenant` runs `scripts/create-tenant`, which creates the team `tenant-acme` and a key for it, and prints the settings an application reads:

```text
LITELLM_BASE_URL=http://127.0.0.1:4400
LITELLM_API_KEY=sk-...
```

| Option (in `TENANT_FLAGS`) | Default | |
|---|---|---|
| `--max-budget USD` | 10 | The team's budget per period |
| `--budget-duration D` | `30d` | The period the budget resets on, such as `30d` or `7d` |
| `--rpm-limit N`, `--tpm-limit N` | None | Requests and tokens per minute, for the team |
| `--models A,B` | All | The model names the team may use |
| `--key-alias NAME` | `<tenant>-default` | The key's alias, unique on the proxy |
| `--allow-mock-responses` | Off | Let the team's keys ask for a mocked reply; for smoke tests only |
| `--quiet` | Off | Print only the new key |

It is safe to run again: the team is looked up by its id and kept as it is, and a key is created only for a new alias, since a key's secret can't be read back after it is shown. To change an existing team's budget, use the admin UI or the proxy's `/team/update` API. Tenant names are lowercase letters, digits and dashes.

## Calling it

It is the OpenAI API, so any OpenAI SDK works, with `base_url` set to the gateway and the tenant's key as the API key:

```bash
curl http://localhost:4400/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model": "default", "guardrails": ["pii-mask", "prompt-injection"],
       "messages": [{"role": "user", "content": "Summarise our launch plan."}]}'
```

The libraries' `[litellm]` extras do the same through pydantic-ai, with `litellm_model("default")`, and the application template wires them to the tenant's key. Responses carry headers that show what the gateway did: `x-litellm-model-group`, `x-litellm-response-cost` and `x-litellm-applied-guardrails`.

Responses are cached for 10 minutes, so an identical request inside that time is answered from the cache.

## Guardrails

Two guardrails are defined once, in the proxy, and chosen per request with `"guardrails": [...]` in the request body. Both are off unless a request asks for them.

| Guardrail | What it does |
|---|---|
| `pii-mask` | Masks email addresses, US phone and social security numbers, Visa, Mastercard and Amex card numbers, and AWS and GitHub credentials, before the request reaches the model |
| `prompt-injection` | Blocks jailbreak, system-prompt and data-exfiltration attempts at medium severity and above, with HTTP 400 naming the guardrail |

Both are LiteLLM's content filter, which is open source and runs in the proxy, with no other service. Attaching guardrails to a team or a key needs LiteLLM's Enterprise licence, so the libraries choose them per request instead, from each workspace's or rule's policy; an application that doesn't ask gets none. `make validate` checks that every guardrail uses an integration that needs no licence, since the proxy starts without a guardrail it can't load, and the smoke test checks that the running proxy loaded both.

## Telemetry

With the `observability` profile, the proxy sends traces and metrics to the Collector over OTLP HTTP, as the service `litellm`:

- **Traces continue the caller's.** The proxy reads the request's `traceparent` header, so one trace runs from the application through the proxy to the provider call, in Tempo and in Langfuse. Prompts and responses are not put on spans.
- **Metrics:** `gen_ai_client_token_usage`, `gen_ai_usage_cost_USD` and `gen_ai_client_operation_duration_seconds`, labelled by model, provider and the tenant's team (`metadata_user_api_key_team_id`), but not by key, so they don't grow a series per key.

Without `observability`, `make up` turns both off, so the proxy doesn't log export errors.

## State

- **Its database** is `litellm`, on the database adapter, created by `db-init`: teams, keys, budgets and spend.
- **Routing state and the response cache** are in database 1 of the shared Valkey (`redis`), whose database 0 is Langfuse's.
- **Two secrets in `.env`:** `LITELLM_MASTER_KEY`, which administers the proxy, and `LITELLM_SALT_KEY`, which encrypts the credentials the proxy stores. Never change the salt key once the proxy has data.

The proxy uses the model prices bundled with its release, so costs don't depend on a network fetch, and reads no `.env` of its own.
