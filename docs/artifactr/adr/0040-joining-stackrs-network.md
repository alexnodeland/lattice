# ADR-0040: Joining stackr's network when it runs

**Status:** Accepted; partly superseded by [lattice ADR-0009](../../adr/0009-one-dev-container-at-the-root.md)
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[ADR-0030](0030-compose-and-dev-containers.md) builds the dev container on the contributor Compose file. When stackr's stack is running, the container should join its network and send telemetry to its Collector; otherwise it should work alone. stackr's Compose project names its default network `stackr`, so other projects can join it as an external network. Compose has no optional external networks: a service that joins a missing one fails to start. Creating the network ahead of stackr does not work either, because stackr's own Compose project then refuses a network it did not create.

## Decision

- **The dev container's `initializeCommand` writes an override on the host**, `.devcontainer/stackr.generated.yaml` (ignored by git):
  - When the `stackr` network exists, the override joins it and sets `OTEL_EXPORTER_OTLP_ENDPOINT` and `LANGFUSE_BASE_URL` to stackr's services.
  - Otherwise the override is empty.
- **docplan joins through an explicit overlay**, `compose.stackr.yaml`, added with `-f` while stackr runs.
- **`make pg-up` starts `compose.yaml`'s PostgreSQL**, so the tests, the dev container and docplan use one definition.

## Options considered

| Option | Works without stackr | stackr starts afterwards |
|---|---|---|
| **An override written before the container is created (chosen)** | Yes | Yes; rebuild the container to join |
| An external network in the Compose file | No: the container fails to start | Yes |
| Creating the `stackr` network if missing | Yes | No: stackr's project refuses the network |
| Joining by hand with `docker network connect` | Yes | Yes, by hand every time |

## Consequences

- Easier: one dev container for both cases, and the tests need nothing from stackr.
- Harder: a container created before stackr started needs a rebuild to join it.

## Action items

1. [x] `compose.yaml`, `compose.stackr.yaml`, the Compose-based dev container, and CI validation.
