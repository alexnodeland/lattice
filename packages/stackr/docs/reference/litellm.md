# LiteLLM configuration

The gateway's configuration is `deploy/litellm/config.yaml`, mounted read-only into the `litellm` service ([The LLM gateway](../guides/gateway.md)). A value `os.environ/NAME` is read from the service's environment, which `compose.yaml` sets from `.env`; `make validate` checks that every one of them is set there, and that no key is written into the file.

## Models

Applications name a model group or an alias from the first column, never a provider's model.

<!-- generated: litellm-models -->

| Model name | Routes to | Key | API base |
|---|---|---|---|
| `claude-sonnet` | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | the provider's |
| `claude-opus` | `anthropic/claude-opus-4-7` | `ANTHROPIC_API_KEY` | the provider's |
| `claude-haiku` | `anthropic/claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` | the provider's |
| `gpt-4o` | `openai/gpt-4o` | `OPENAI_API_KEY` | the provider's |
| `gpt-4o-mini` | `openai/gpt-4o-mini` | `OPENAI_API_KEY` | the provider's |
| `gemini-2.5-pro` | `gemini/gemini-2.5-pro` | `GEMINI_API_KEY` | the provider's |
| `gemini-2.5-flash` | `gemini/gemini-2.5-flash` | `GEMINI_API_KEY` | the provider's |
| `openrouter/*` | `openrouter/*` | `OPENROUTER_API_KEY` | the provider's |
| `lmstudio` | `lm_studio/local-model` | a placeholder | `LM_STUDIO_API_BASE` |
| `omlx/*` | `openai/*` | a placeholder | `OMLX_API_BASE` |
| `default` | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` | the provider's |
| `fast` | `anthropic/claude-haiku-4-5-20251001` | `ANTHROPIC_API_KEY` | the provider's |

<!-- end generated -->

A model whose key is empty in `.env` fails, and its group falls back. LM Studio and oMLX need no key; the file gives them placeholders.

## Fallbacks

<!-- generated: litellm-fallbacks -->

| Model group | Falls back to, in order |
|---|---|
| `default` | `gpt-4o` then `gemini-2.5-pro` |
| `fast` | `gpt-4o-mini` then `gemini-2.5-flash` |

<!-- end generated -->

## Guardrails

Requests choose guardrails with `"guardrails": [...]` in their body.

<!-- generated: litellm-guardrails -->

| Guardrail | Integration | Mode | On by default | Checks |
|---|---|---|---|---|
| `pii-mask` | `litellm_content_filter` | `pre_call` | no | email (mask), us_phone (mask), us_ssn (mask), visa (mask), mastercard (mask), amex (mask), aws_access_key (mask), aws_secret_key (mask), github_token (mask) |
| `prompt-injection` | `litellm_content_filter` | `pre_call` | no | prompt_injection_jailbreak (block at medium), prompt_injection_system_prompt (block at medium), prompt_injection_data_exfiltration (block at medium) |

<!-- end generated -->

## Settings

<!-- generated: litellm-settings -->

| Setting | Value |
|---|---|
| `router_settings.routing_strategy` | `simple-shuffle` |
| `router_settings.num_retries` | `2` |
| `router_settings.allowed_fails` | `3` |
| `router_settings.cooldown_time` | `30` |
| `router_settings.redis_url` | `os.environ/REDIS_URL` |
| `litellm_settings.drop_params` | `true` |
| `litellm_settings.request_timeout` | `600` |
| `litellm_settings.cache` | `true` |
| `litellm_settings.cache_params.type` | `redis` |
| `litellm_settings.cache_params.redis_url` | `os.environ/REDIS_URL` |
| `litellm_settings.cache_params.ttl` | `600` |
| `callback_settings.otel.attributes.exclude_list` | `[metadata.user_api_key_hash, metadata.user_api_key_alias, hidden_params]` |
| `general_settings.master_key` | `os.environ/LITELLM_MASTER_KEY` |
| `general_settings.database_url` | `os.environ/DATABASE_URL` |

<!-- end generated -->

`REDIS_URL` is database 1 of the shared Valkey, and `DATABASE_URL` the `litellm` database on the database adapter, both set in `compose.yaml`.

## The file

??? example "The whole file: `deploy/litellm/config.yaml`"

    ```yaml
    --8<-- "deploy/litellm/config.yaml"
    ```
