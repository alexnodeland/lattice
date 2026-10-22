# ADR-0028: Local Supabase on the loopback

**Status:** Accepted, amended by [ADR-0045](0045-local-supabase-only-where-docker-keeps-it-on-the-loopback.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0009](0009-local-supabase-as-the-database-adapter.md): local Supabase's ports are no longer the exception to [ADR-0006](0006-networks-and-published-ports.md)'s `STACKR_BIND`.

> **Amended by [ADR-0045](0045-local-supabase-only-where-docker-keeps-it-on-the-loopback.md):** some engines, Docker Desktop 29 among them, ignore `host_binding_ipv4` and publish on every interface. `make up` now probes where Docker publishes on this network before it starts Supabase, and refuses to start it anywhere but `STACKR_BIND`, with no override: on such an engine, run on the `postgres` adapter with the `auth` profile.

## Context

ADR-0009 recorded that the Supabase CLI publishes local Supabase's ports on every interface, with no setting to bind them to `127.0.0.1`. That holds for its flags: the CLI (2.118.0) publishes each port with a host port and no host address. But Docker publishes such a port at its network's default address, `com.docker.network.bridge.host_binding_ipv4`, and the CLI runs Supabase on `supabase_network_stackr-supabase`, which `make up` already creates before `supabase start`. Supabase's own documentation advises this way of keeping its ports on the loopback. Its keys are well known and its database password is `postgres`, so every interface means anyone who can reach the machine can read and write its database.

## Decision

- **`make up` creates Supabase's network with `host_binding_ipv4` set to `STACKR_BIND`,** `127.0.0.1` unless you choose, so local Supabase publishes where every other port of the stack does. Reaching it from the local network is an opt-in, as for the rest: set `STACKR_BIND` to a LAN address.
- **A network made before, or for another address, is refused:** `make up` says to `make down`, remove the network, and start again, since a network's options can't change.
- **`make smoke` checks it:** on the `supabase` adapter, Supabase's containers publish only at `STACKR_BIND`.

## Consequences

- Easier: no firewall rule is needed to keep a workstation's Supabase to itself.
- Harder: changing `STACKR_BIND` means removing Supabase's network, once.
