# ADR-0047: An upstream gateway for the model groups

**Status:** Accepted, amended by [ADR-0054](0054-prompt-cache-breakpoints-at-the-gateway.md)
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

Amends [ADR-0010](0010-the-llm-gateway.md)'s model groups.

## Context

Running the stack against models served elsewhere, such as an OpenAI-compatible gateway on the home network with a certificate from its own authority, took an untracked `compose.override.yaml` and a copy of `config.yaml`. That was a second gateway config, kept in step with the first by hand.

LiteLLM's config has no conditions, so a group can't be switched on or off with a setting. Two deployments in one group would be balanced between, the upstream's and Anthropic's.

## Decision

- **The model groups are a file of their own, chosen in `.env`.** `config.yaml` includes `groups.yaml`, which Compose mounts from `deploy/litellm/groups/` as `STACKR_GATEWAY_MODELS` says:
  - `providers`, the default: `default` and `fast`, as before.
  - `upstream`: the groups are `STACKR_UPSTREAM_DEFAULT_MODEL` and `STACKR_UPSTREAM_FAST_MODEL` at `STACKR_UPSTREAM_URL`, with `STACKR_UPSTREAM_API_KEY`. Any other of its models is `upstream/<model>`.
- **`STACKR_UPSTREAM_CA`,** a PEM file on the host, is mounted, and `deploy/litellm/ca-upstream.env` makes it the proxy's `SSL_CERT_FILE`. Without it, that env file isn't read and nothing is set.
- **`make` refuses any other value of `STACKR_GATEWAY_MODELS`.** `scripts/check-config` holds both files to the same two groups, and to nothing but a model list. LiteLLM's `include` extends lists and replaces any other key whole. `scripts/check-make` tests both refusals.
- **The AWS recipe's thin image, `stackr-litellm`, has no Compose mount,** so it bakes the providers' groups as `groups.yaml`. An upstream gateway there means building it with `groups/upstream.yaml` in their place, which the recipe doesn't do yet.

## Options considered

- **Every group in one config:** both deployments would be balanced between, as above.
- **A second whole config:** it would duplicate the guardrails, the router's settings and the cache.

A file of nothing but the groups is the smallest choice.

## Consequences

- Easier: running the stack against a gateway of one's own takes five lines of `.env`.
- Harder: changing `default` is a change to `groups/providers.yaml`, not `config.yaml`. With `STACKR_UPSTREAM_CA` set, the proxy trusts that authority alone, so the providers' own certificates stop verifying.
- To revisit: a CA bundle that adds the upstream's authority to the public ones, if both are wanted at once; the upstream in the AWS recipe.
