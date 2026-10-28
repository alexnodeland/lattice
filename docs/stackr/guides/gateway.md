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

A group can hold several deployments, which the router balances (`simple-shuffle`). A failed request is retried twice, a deployment that fails three times is cooled down for 30 seconds, and a group that still fails falls back to the next group in its list. Changing what `default` means is a change to `groups/providers.yaml`, for every application at once.

### Provider keys

Put the keys of the providers you use in stackr's `.env`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`. A model whose key is empty fails, and the router falls back; the others still work. After changing a key, run `make up` again: Compose recreates the proxy with its new environment, which `docker compose restart` would not.

### Local model servers

The proxy reaches servers on this machine through `host.docker.internal`, which Compose maps to the host on every platform:

| Model name | Setting | Default |
|---|---|---|
| `lmstudio` | `LM_STUDIO_API_BASE` | `http://host.docker.internal:1234/v1`, LM Studio's server |
| `omlx/<model>` | `OMLX_API_BASE` | `http://host.docker.internal:4243/v1`, oMLX's OpenAI-compatible server |

### An upstream gateway

`default` and `fast` can be another OpenAI-compatible API's models instead of the providers': a gateway of your own in front of your own models, for example ([ADR-0047](../adr/0047-an-upstream-gateway-for-the-model-groups.md)). Set, in `.env`:

| Setting | What it is |
|---|---|
| `STACKR_GATEWAY_MODELS` | `upstream`, rather than `providers`: the groups in `deploy/litellm/groups/upstream.yaml` |
| `STACKR_UPSTREAM_URL` | Its API's base, with `/v1`, as the proxy's container reaches it |
| `STACKR_UPSTREAM_API_KEY` | Its key |
| `STACKR_UPSTREAM_DEFAULT_MODEL`, `STACKR_UPSTREAM_FAST_MODEL` | Its models for `default` and `fast` |
| `STACKR_UPSTREAM_CA` | If its certificate is signed by an authority of your own, that authority's PEM file, a path on this machine |

Any other of its models is `upstream/<model>`. The aliases above stay, and so do the fallbacks: a group whose upstream fails falls back to the providers', which fail too without their keys. With `STACKR_UPSTREAM_CA` set, the proxy trusts that authority alone, so the providers' public certificates stop verifying: use it when the upstream is what you call. Run `make up` again after changing any of these.

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

It reaches the gateway, and prints its address, where the stack publishes it: at `STACKR_BIND` when that names one address, and at `127.0.0.1` when it is `0.0.0.0`, every interface.

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

### The portal's key

portalr's admin shows each tenant's spend and budget from the gateway. That is a read of a team's info, the list of teams, and the daily activity of a team and of the workspaces' tags, which the master key opens, and so does everything else; the master key must never reach an application. `make portal-key` makes the application a key of its own:

```bash
make portal-key      # prints PORTAL_LITELLM_KEY=sk-...
```

It creates a user, `portalr`, whose role is the proxy's view-only admin, and a key, `portal-spend-read`, that belongs to it and is limited with `allowed_routes` to `/team/info`, `/team/list`, `/team/daily/activity` and `/tag/daily/activity`. Both parts are needed: a key with no user can't read a team it is not in, and the role alone would let the key read other keys and the spend logs. On the pinned LiteLLM (v1.103.0) the key reads those four routes and is refused every other one: chat, creating or updating keys and teams, and reading keys or spend logs. Like a tenant's key, it is shown once and the command is safe to run again. Put it in the application's `.env` as `PORTAL_LITELLM_KEY`, which holds secrets: keep the file mode 0600.

The key's value can't be read back. If it is lost, `make portal-key ARGS=--rotate` deletes `portal-spend-read` by its alias and makes another; the lost one stops working. The two steps are not atomic: between them, and until the new key is in the application's `.env` and the application restarted, the portal's spend reads fail with `unavailable`. Without `--rotate`, when the key exists, the command says so, and with `--quiet` it exits with status 3 and prints nothing, so a script can't take an empty value for a key.

**A leaked key reads every tenant's spend and teams.** The routes are not scoped to one tenant: `/team/list` returns every team, and `/team/info` any team's, with their budgets, members and spend. It can't call a model or change anything, but treat it like any secret: keep it out of images and logs, and rotate it when it may have leaked.

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

## Prompt caching

That response cache is not a prompt cache. It answers a request that is identical, word for word, to one in the last 10 minutes, from the gateway's Valkey, without calling the provider. A prompt cache is the provider's: it keeps the processed prefix of a prompt, so a request that starts the same way, such as the next turn of a conversation, pays less for that prefix and is answered sooner.

Anthropic caches only up to a `cache_control` breakpoint in the request, and the OpenAI-compatible clients that call the gateway, pydantic-ai's included, never send one. So the gateway adds two to the Anthropic groups, `default` and `fast`, in `deploy/litellm/groups/providers.yaml` ([ADR-0054](../adr/0054-prompt-cache-breakpoints-at-the-gateway.md)): on the system prompt, and on the last message. On the next turn, Anthropic looks back from the new last message's breakpoint (up to 20 blocks) for the longest prefix it has cached, so it reads the conversation so far and writes only what is new. A step that adds more than 20 content blocks between breakpoints misses, and writes the prefix again. Nothing else gets them: the aliases in `config.yaml`, the other providers and the upstream groups are as they were.

Two limits:

- **An assistant message that only calls tools,** with no text, takes no breakpoint. The last message of a request is a user turn or a tool result, so the groups' points aren't affected; a point by index on such a message would be lost.
- **Anthropic allows four breakpoints a request.** The proxy's LiteLLM (v1.103.0) skips a message the client already marked and stops at four, counting the client's own, so the gateway never pushes a request past four (from its source, not tested here). A 400 about `cache_control` means the client's own marks exceed it: look at the client, not the gateway.

What it costs, from [Anthropic's prompt caching documentation](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching) (read on 2026-10-27, when this was written):

- **A cache entry lives 5 minutes,** refreshed each time it is read. A conversation idle longer starts again from a write.
- **Writing costs about 1.25 times the input price, reading about 0.1 times.** A prefix read once more within the 5 minutes has paid for its write.
- **Short prompts aren't cached:** below 1,024 tokens on Sonnet 4.6 (`default`) and 4,096 on Haiku 4.5 (`fast`), the request goes through uncached, with no error.

To see it working, look at a request's usage. LiteLLM reads Anthropic's `cache_read_input_tokens` and `cache_creation_input_tokens` into its usage, and pydantic-ai has `cache_read_tokens` and `cache_write_tokens` on a run's usage; whether the numbers reach the application through the gateway (whose LiteLLM is newer than the libraries' client), and Langfuse's generation view, hasn't been checked yet. To check by hand: send a request above the minimum, then within 5 minutes the same messages with one more user turn (so the response cache can't answer it), and compare the two responses' `usage`.

## Guardrails

Two guardrails are defined once, in the proxy, and chosen per request with `"guardrails": [...]` in the request body. Both are off unless a request asks for them.

| Guardrail | What it does |
|---|---|
| `pii-mask` | Masks email addresses, US phone and social security numbers, Visa, Mastercard and Amex card numbers, and AWS and GitHub credentials, before the request reaches the model |
| `prompt-injection` | Blocks jailbreak, system-prompt and data-exfiltration attempts at medium severity and above in tool results, with HTTP 400 naming the guardrail |

Both are LiteLLM's content filter, which is open source and runs in the proxy, with no other service. Attaching guardrails to a team or a key needs LiteLLM's Enterprise licence, so the libraries choose them per request instead, from each workspace's or rule's policy; an application that doesn't ask gets none. `make validate` checks that every guardrail uses an integration that needs no licence, since the proxy starts without a guardrail it can't load, and the smoke test checks that the running proxy loaded both.

`prompt-injection` reads only tool results (`scan_only_tool_results: true`): the text an agent's tools bring back, such as a fetched page or a file's contents, which is where an injection that the person didn't write comes in. It doesn't read the person's prompt, the system prompt, or the model's own replies and tool arguments. Its word lists are a heuristic: a word such as "enter" and one such as "unlimited" in one sentence is a jailbreak to them, so when they read every message, a landing page the model wrote into a tool call blocked the next request of the turn, and every later request of the thread, since each one carries the thread's history ([ADR-0010's amendment](../adr/0010-the-llm-gateway.md#amendment-2026-10-27-prompt-injection-reads-tool-results)). A tool result that repeats such a page, like a file read of it, can still be blocked.

A block shows in the proxy's log, with the category and the words that matched:

```sh
docker compose logs --since 1h litellm 2>&1 | grep -i 'content blocked'
```

A request with no tool result is not scanned by `prompt-injection` at all.

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
