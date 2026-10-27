# ADR-0054: Prompt-cache breakpoints at the gateway

**Status:** Accepted
**Date:** 2026-10-27
**Deciders:** Alex Nodeland

Amends [ADR-0047](0047-an-upstream-gateway-for-the-model-groups.md)'s providers' groups.

## Context

The libraries call the gateway through pydantic-ai's OpenAI chat model, which never sends Anthropic's `cache_control`. Anthropic caches a prompt only up to such a breakpoint, so `default` and `fast` paid full input on every turn of an agent loop, though each turn repeats the one before.

The gateway's 10-minute response cache doesn't help: it answers only a request identical to an earlier one, and the next turn never is.

LiteLLM (the proxy image pins v1.103.0) adds breakpoints itself with `cache_control_injection_points` in a deployment's `litellm_params`, for `/v1/chat/completions`. A point is a message by role, or by index from the end. It skips a point past Anthropic's four breakpoints, counting the client's own.

## Decision

- **`default` and `fast` in `groups/providers.yaml` carry three points:** the system prompt, and the messages at `-2` and `-1`. The last message holds the newest turn, and the one before it the prefix the previous turn wrote, so each request reads that and writes only what is new.
- **Nothing else gets them:** not the aliases in `config.yaml`, not the other providers, which cache their own way, and not `groups/upstream.yaml`, whose models are behind an OpenAI-compatible API that may reject the field.
- **`scripts/check-config litellm` holds the groups to it:** an Anthropic deployment in `groups/` without exactly these points, or any other with points at all, fails `make validate`.

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

**Pros:** one line.
**Cons:** global, so the aliases and anything added later change too; and it stands down whenever a client sends its own breakpoint.

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
- To revisit: Anthropic's 1-hour TTL for long idle threads; points on the `claude-*` aliases; and that the cache tokens reach pydantic-ai's usage and Langfuse through the proxy, which is checked by hand so far.

## Action items

1. [x] Points on `default` and `fast`, and the check.
2. [ ] By hand, on a running stack: a second identical request (past the response cache) reports `cache_read_input_tokens` above zero.
