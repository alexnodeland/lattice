# ADR-0009: One dev container, at the root

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Supersedes the dev containers of [artifactr ADR-0030](../artifactr/adr/0030-compose-and-dev-containers.md) and [reflexr ADR-0021](../reflexr/adr/0021-contributor-compose-and-dev-containers.md), and the override that joined them to stackr's network in [artifactr ADR-0040](../artifactr/adr/0040-joining-stackrs-network.md) and [reflexr ADR-0037](../reflexr/adr/0037-joining-stackrs-network.md).

## Context

[RFC-0003's Dev container section](../stackr/rfcs/0003-one-repository-lattice.md#dev-container) replaces the packages' dev containers with one at the root, running Docker inside it, and supersedes artifactr ADR-0030 and reflexr ADR-0021. The setup brought a basic container, and phase 7 brings the rest. The RFC left two things unsaid: what the basic container is built on, and what becomes of artifactr ADR-0040 and reflexr ADR-0037. Those built each library's container on its contributor `compose.yaml`, and their `initializeCommand` wrote an override that joined the container to the `stackr` network when stackr's stack was running.

## Decision

- **The container is an image, not a Compose service:** `mcr.microsoft.com/devcontainers/base:jammy`, with the GitHub CLI, Node, which runs the Supabase CLI through `npx`, and Docker-in-Docker.
- **It is built on nothing in the packages:** no Compose file, no `initializeCommand`, and no package's environment.
- **The override retires.** stackr's stack runs on the container's own Docker, so its published ports are the container's, such as the Collector's at `localhost:4317`. A reference implementation still joins the `stackr` network through its library's `compose.stackr.yaml`, on the same Docker.
- **The rest of those ADRs stands:** each library's contributor `compose.yaml` and `compose.stackr.yaml`.

## Consequences

- Easier: one container, which no package's files can break, opens the whole family.
- Harder: its Docker starts empty. Images the host already has are pulled again inside, and a stack started on the host isn't visible from the container.
- Harder: nothing builds the container in CI until phase 7's prebuilt image, so a change that breaks it shows only when someone rebuilds it.
