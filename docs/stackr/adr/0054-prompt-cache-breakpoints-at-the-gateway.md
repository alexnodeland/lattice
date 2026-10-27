# ADR-0054: Prompt-cache breakpoints at the gateway

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland

Amends [ADR-0047](0047-an-upstream-gateway-for-the-model-groups.md): the providers' groups in `groups/providers.yaml` carry more than a model and a key.

## Context

The libraries call the gateway through pydantic-ai's OpenAI chat model, which never sends Anthropic's `cache_control`. Anthropic caches a prompt only up to such a breakpoint, so `default` and `fast` paid full input on every turn of an agent loop, though each turn repeats the one before.

The gateway's 10-minute response cache doesn't help: it answers only a request identical to an earlier one, and the next turn never is.

LiteLLM adds breakpoints itself with `cache_control_injection_points` in a deployment's `litellm_params`, for `/v1/chat/completions`: a point is a message by role, or by index from the end. In the proxy image's version, v1.103.0, its source (`litellm/integrations/anthropic_cache_control_hook.py`) skips a message the client already marked and stops at Anthropic's four breakpoints, counting the client's own. The libraries' client pins an older LiteLLM, 1.83.0, without that cap; the tests run its hook, which places the points the same way.

## Decision

- **`default` and `fast` in `groups/providers.yaml` carry two points:** the system prompt and the last message, LiteLLM's own default. On the next turn Anthropic looks back up to 20 blocks from the new last breakpoint for the longest prefix it cached, so it reads the conversation so far and writes only what is new. A point on the message before the last would write a strict prefix of what the last one writes, spend a slot, and with two messages land on the system prompt again.
- **Nothing else gets them:** not the aliases in `config.yaml`, not the other providers, which cache their own way, and not `groups/upstream.yaml`, whose models are behind an OpenAI-compatible API that may reject the field.
- **`scripts/check-config litellm` holds the groups to it:** an `anthropic/` deployment in `groups/` without at least these two points (a `control`, such as a TTL, and more points are allowed), or any other deployment with points at all, fails `make validate`.

## Options considered

### Option A: Breakpoints in the libraries

| Dimension | Assessment |
|---|---|
| Complexity | Medium |
| Reach | Only callers through the libraries |

**Pros:** the caller knows its prompt's stable parts.
**Cons:** pydantic-ai's OpenAI model has no place for them; every client would need its own.

### Option B: `enable_anthropic_prompt_caching`, LiteLLM's global switch

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Reach | Every Anthropic model on the gateway |

**Pros:** one line, the same two points.
**Cons:** global, so the aliases and anything added later change too.

### Option C: Points on the two groups (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low |
| Reach | `default` and `fast` |

**Pros:** explicit, per group, checked by `make validate`.
**Cons:** a new Anthropic group has to copy them.

## Trade-off analysis

The groups are what applications ask for, so they are where the savings are; the points are config, checked like the rest of it, and touch no other model.

## Consequences

- Easier: a long conversation on `default` or `fast` reads its history from Anthropic's cache, at about 0.1 times the input price, for 5 minutes after its last use (Anthropic's documentation, verified on 2026-10-27).
- Harder: each new prefix is written at about 1.25 times the input price, so a one-off request costs a little more. Prompts below Anthropic's minimum (1,024 tokens on Sonnet 4.6, 4,096 on Haiku 4.5) aren't cached.
- Limits: an assistant message that only calls tools, with no text, takes no breakpoint (the last message of a request is a user turn or a tool result, so the two points aren't affected). The check recognises only `anthropic/` models: a Claude group on Bedrock or Vertex would need adding to it. The four-breakpoint cap with a client that marks its own, such as Claude Code, is from LiteLLM's source, not tested here.
- To revisit: Anthropic's 1-hour TTL for long idle threads; points on the `claude-*` aliases; that the cache tokens reach pydantic-ai's usage (client LiteLLM 1.83.0, proxy 1.103.0) and Langfuse, which is unverified.

## Action items

1. [x] Points on `default` and `fast`, and the check.
2. [ ] By hand, on a running stack: a request above the minimum, then within 5 minutes the same messages with one more user turn (so the response cache can't answer it); the second reports `cache_read_input_tokens` above zero.
