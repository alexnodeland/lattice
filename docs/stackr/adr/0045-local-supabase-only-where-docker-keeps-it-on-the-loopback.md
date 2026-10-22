# ADR-0045: Local Supabase only where Docker keeps it on the loopback

**Status:** Accepted
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

Amends [ADR-0028](0028-local-supabase-on-the-loopback.md).

## Context

ADR-0028 keeps local Supabase's ports on the loopback by creating its network with `com.docker.network.bridge.host_binding_ipv4` set to `STACKR_BIND`. On Docker Desktop 29.4, a container on such a network that publishes a port with no address of its own publishes it at `0.0.0.0` and `::` all the same. `make smoke` caught it: Supabase's API, Studio and PostgreSQL (54321 to 54324) were on every interface, with Supabase's well-known keys and the password `postgres`.

The Supabase CLI (2.118.0) still has no flag for the address. Nothing `make up` can set fixes it; it can only find out before Supabase starts.

## Decision

- **`make up` probes before local Supabase starts.** On the `supabase` adapter, after it has made Supabase's network, `scripts/binding-probe` does four things:
  - runs a container that runs nothing: `sleep`, in the curl image the stack already pins, read-only, with no capabilities;
  - has it publish one port on that network;
  - reads where Docker published the port, IPv4 and IPv6;
  - removes the container.
- **Supabase starts only if that port is at `STACKR_BIND` alone.** Otherwise `make up` doesn't start it and says to run on the `postgres` adapter with the `auth` profile, whose ports Compose publishes at `STACKR_BIND` explicitly. A probe that can't run (Docker down, its image not pulled with no network) refuses the same way: closed, with stackr's own message.
- **There is deliberately no override.** It follows that `STACKR_BIND=0.0.0.0` with local Supabase is now always refused, on every engine: the probe's port is then at `0.0.0.0` and `::`, every interface, which is what it refuses. No setting starts local Supabase on an engine that publishes it elsewhere. The owner's rule is that local binds stay on the loopback, and the supported way on such an engine is `STACKR_DATABASE=postgres` with the `auth` profile.
- `make smoke`'s check after the fact stays. `scripts/check-make` tests the probe against a fake `docker`, for each shape an engine publishes in.

## Options considered

### Option A: probe, and refuse (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one container, a few seconds |
| Exposure | None: what is published, for a moment, is a port nothing listens on |

**Pros:** it finds the engine's behaviour, not its version. An engine that honours the option keeps Supabase, and one fixed later gets it back with no change.
**Cons:** on such an engine, local Supabase is not available at all.

### Option B: check after `supabase start`, and stop it

**Cons:** Supabase's database is open, with its known password, while it starts and until it is stopped.

### Option C: make `postgres` the default adapter

**Cons:** it changes what stackr is out of the box ([ADR-0009](0009-local-supabase-as-the-database-adapter.md)), on every engine, to work round one. That is the owner's to decide, and isn't decided here.

### Option D: an override, to accept the exposure

**Cons:** it would break the rule this exists to keep, for anyone who sets it once and forgets.

## Consequences

- Easier: on an engine that ignores the option, `make up` says so, and what to do, before anything is open.
- Harder: on such an engine, local Supabase can't be had at all; Studio and Supabase's own Auth with it.
- To revisit: the default adapter, if more engines turn out to ignore the option.
