# ADR-0009: One dev container, at the root

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Supersedes the dev containers of [artifactr ADR-0030](../artifactr/adr/0030-compose-and-dev-containers.md) and [reflexr ADR-0021](../reflexr/adr/0021-contributor-compose-and-dev-containers.md), and the override that joined them to stackr's network in [artifactr ADR-0040](../artifactr/adr/0040-joining-stackrs-network.md) and [reflexr ADR-0037](../reflexr/adr/0037-joining-stackrs-network.md).

## Context

Each of the four established repositories had a dev container. artifactr's and reflexr's were built on their contributor `compose.yaml`, with the test environment set (artifactr ADR-0030, reflexr ADR-0021), and their `initializeCommand` wrote an override that joined the container to the `stackr` network when stackr's stack was running (artifactr ADR-0040, reflexr ADR-0037). In lattice, one checkout holds every package, with one environment and one lock, and the old containers broke with the new layout.

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#dev-container) plans one dev container at the root, with an egress firewall for unattended agents, the Claude Code and Git AI features, a prebuilt image and Codespaces in phase 7, and a basic container in the setup. This records the basic container, and what it replaces.

## Decision

- **One dev container, in `.devcontainer/` at lattice's root,** for every package: Ubuntu (`mcr.microsoft.com/devcontainers/base:jammy`) with the GitHub CLI, Node, which runs the Supabase CLI through `npx`, and Docker.
- **Docker runs inside it** (Docker-in-Docker), for stackr's stack, the reference implementations and the PostgreSQL tests. What a contributor starts there runs on the container's own Docker, and its published ports are the container's: stackr's Collector is at `localhost:4317`, and a library's PostgreSQL, from its `pg-up` task, at its usual port. A reference implementation joins stackr's `stackr` network through its library's `compose.stackr.yaml`, on the same Docker.
- **It is built on nothing in the packages:** no Compose file, no `initializeCommand` and no package's environment. `post-create.sh` installs proto, which installs moon and uv at the versions in `.prototools`; then uv installs Python 3.12, 3.13 and 3.14, the workspace is synced with every package, group and extra, and prek installs the hooks, as `make install` does.
- **The editor** formats Python with ruff on save, and has the moon, Docker, YAML, TOML, ShellCheck, Markdown and Mermaid extensions. Port 8000, where the reference implementations and the docs site serve, is forwarded.
- **What those ADRs decided besides the dev container stands:** each library's contributor `compose.yaml`, with PostgreSQL and its reference implementation under the `app` profile, and `compose.stackr.yaml`.

## Options considered

| Option | Opens the whole family | Reaches stackr's stack | To maintain |
|---|---|---|---|
| **One container at the root, with Docker inside (chosen)** | Yes: one checkout, one environment | On its own Docker, at `localhost` | One |
| The four containers, each on its package's Compose file | No, and they broke with the root's lock and layout | By joining the `stackr` network through an override | Four |
| One container on the host's Docker socket | Yes | By joining the `stackr` network, as before | One, sharing the host's containers and their ports |

## Consequences

- Easier: one container opens the family, and runs everything CI runs, stackr's smoke tests included.
- Harder: its Docker starts empty. Images the host already has are pulled again inside, and a stack started on the host isn't visible from the container.
- Harder: nothing builds the container in CI yet, so a change that breaks it shows only when someone rebuilds it. Phase 7's prebuilt image, built and checked by CI, closes that.
- Revisit in phase 7: the firewall, the Claude Code and Git AI features, `devcontainer-lock.json`, the prebuilt image and Codespaces, as RFC-0003 plans them.
