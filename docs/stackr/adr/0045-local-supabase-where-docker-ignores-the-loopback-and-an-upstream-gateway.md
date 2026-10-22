# ADR-0045: Local Supabase where Docker ignores the loopback, and an upstream gateway

**Status:** Accepted
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

Amends [ADR-0028](0028-local-supabase-on-the-loopback.md), and [ADR-0010](0010-the-llm-gateway.md)'s model groups.

## Context

Two things a workstation running stackr met, both found running it on Docker Desktop 29.4.

**Docker 29 ignores `host_binding_ipv4`.** ADR-0028 keeps local Supabase's ports on the loopback by creating its network with `com.docker.network.bridge.host_binding_ipv4` set to `STACKR_BIND`. On Docker Desktop 29.4 a container on such a network, publishing a port with no address of its own, publishes it at `0.0.0.0` and `::` all the same. `make smoke` caught it: Supabase's API, Studio and PostgreSQL (54321 to 54324) on every interface, with its well-known keys and the password `postgres`. The Supabase CLI (2.118.0) still has no flag for the address. Nothing `make up` can set fixes it; it can only find out before Supabase starts.

**A gateway of one's own.** Running the stack against models served elsewhere, an OpenAI-compatible gateway on the home network with a certificate from its own authority, took an untracked `compose.override.yaml` and a copy of `config.yaml`: a second gateway config to keep in step with the first, by hand.

## Decision

- **`make up` probes before local Supabase starts.** On the `supabase` adapter, after it has made Supabase's network, it runs a container that runs nothing (`sleep`, in the curl image the stack already pins, read-only, no capabilities) publishing one port on that network, reads where Docker published it, and removes it. If that is anything but `STACKR_BIND` alone, it doesn't start Supabase, and says to run on the `postgres` adapter with the `auth` profile, whose ports Compose publishes at `STACKR_BIND` explicitly. `make smoke`'s check after the fact stays.
- **The model groups are a file of their own, chosen in `.env`.** `config.yaml` includes `groups.yaml`, which Compose mounts from `deploy/litellm/groups/`, as `STACKR_GATEWAY_MODELS` says: `providers` (the default, `default` and `fast` as before) or `upstream`, where they are `STACKR_UPSTREAM_DEFAULT_MODEL` and `STACKR_UPSTREAM_FAST_MODEL` at `STACKR_UPSTREAM_URL` with `STACKR_UPSTREAM_API_KEY`, and any other of its models is `upstream/<model>`. `STACKR_UPSTREAM_CA`, a PEM file on the host, is mounted and becomes the proxy's `SSL_CERT_FILE`. `make` refuses any other value of `STACKR_GATEWAY_MODELS`, and `scripts/check-config` holds both files to the same two groups and to nothing but a model list.

## Options considered

### Option A: probe, and refuse (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one container, a few seconds |
| Exposure | None: what is published, for a moment, is a port nothing listens on |

**Pros:** finds the engine's behaviour, not its version, so an engine that honours the option keeps Supabase, and one that is fixed later gets it back with no change.
**Cons:** on such an engine local Supabase is not available at all.

### Option B: check after `supabase start`, and stop it

**Cons:** Supabase's database is open, with its known password, while it starts and until it is stopped.

### Option C: make `postgres` the default adapter

**Cons:** a change of what stackr is out of the box (ADR-0009), for every engine, to work round one; the owner's to decide, and not decided here.

### For the gateway: one config with every group in it, or a second config file

LiteLLM's config has no conditions, so a group can't be on or off with a setting; two deployments in one group would be balanced between, the upstream's and Anthropic's. A second whole config would duplicate the guardrails, the router's settings and the cache. LiteLLM's `include` extends the model list and replaces any other key whole, so a file of nothing but the groups is the smallest choice.

## Trade-off analysis

Refusing is the only one of the three that never leaves Supabase's database open, and it costs nothing where Docker does what ADR-0028 expects. The groups' file keeps one gateway config, and moves only what differs.

## Consequences

- Easier: on an engine that ignores the option, `make up` says so, and what to do, before anything is open. Running the stack against a gateway of one's own is five lines of `.env`.
- Harder: changing `default` is a change to `groups/providers.yaml`, not `config.yaml`. With `STACKR_UPSTREAM_CA` set, the proxy trusts that authority alone, so the providers' own certificates stop verifying.
- To revisit: the default adapter, if more engines turn out to ignore the option; a CA bundle that adds the upstream's authority to the public ones, if both are wanted at once.

## Action items

1. [x] The probe in `make up`, before `supabase start`.
2. [x] `deploy/litellm/groups/`, `STACKR_GATEWAY_MODELS` and the upstream's settings, checked by `scripts/check-config`.
