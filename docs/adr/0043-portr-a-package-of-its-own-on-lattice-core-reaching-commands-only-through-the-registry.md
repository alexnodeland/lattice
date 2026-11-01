# ADR-0043: portr, a package of its own on lattice-core, reaching commands only through the registry

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** [RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Decision O7, for #917

## Context

RFC-0014 serves all of lattice to outside clients through one gateway per deployment, over MCP and ACP. The gateway must reach every package's commands, carry MCP's SDK, OAuth and ACP, and keep the libraries independent (ADR-0018). The owner decided where it lives on 2026-10-31 (O7): a new package, `portr`, as the RFC recommended. Its options were a package of its own, a `gateway` extra of portalr's, a package importing each library behind extras, or the template.

## Decision

- **`packages/portr`, distributed as `portr-ai`** and imported as `portr`. `portr` and `portr-ai` were both free on PyPI on 2026-10-30. It starts at 0.0.0, and release-please releases it with the others, in the last stage after portalr's, since it will depend on grantr.
- **It depends on lattice-core** (`capabilities` and `commands` now; `approvals` with the elicitation surface) **and on grantr**, for connections, keys and audit, once its OAuth module needs them. portalr depends on grantr the same way.
- **It imports no library:** never artifactr, reflexr, evalr, relayr or portalr. Each library's commands reach portr only through lattice-core's registry, from the providers the application binds at its composition root (ADR-0041). Its layering test asserts this; deptry and `standalone` check it too.
- **Its modules,** as RFC-0014 plans them:
  - `portr.core`: what a client is offered, with no I/O and no MCP SDK.
  - `portr.mcp`: the Streamable HTTP server, behind the `mcp` extra.
  - `portr.oauth`: tokens and the consent API, behind the `mcp` extra.
  - `portr.acp`: ACP permission requests, behind the `acp` extra.
- **The first release holds `portr.core` alone.**
- **Wired in as every package is:**
  - moon's workspace;
  - release-please's configuration and manifest;
  - the release plan's stages;
  - the floors check, which expects portr to fail at lattice-core-ai 0.2.0 until its floor rises;
  - the site's nav, and the README's, AGENTS.md's and SECURITY.md's lists;
  - the issue templates.

## Options considered

### Option A: A package of its own (chosen)

**Pros:** it imports no library, so it sits where portalr does in moon's graph. MCP's SDK, OAuth and ACP stay out of portalr and lattice-core. It releases on its own.
**Cons:** one more package to release and document; a new distribution on PyPI needs its trusted publisher set up before its first release.

### Option B: portalr's `gateway` extra

**Cons:** the gateway's dependencies and its security surface would ship in portalr's wheel, and a deployment without the UIs couldn't run the gateway without portalr.

### Option C: A package importing each library behind extras

**Cons:** portr would pin every library's API and release with each; the libraries' commands would live in portr, not beside their code; the registry would be bypassed.

## Consequences

- Easier: the gateway grows in its own package, phase by phase, with its own layering test.
- Harder: one more package in every list, and PyPI's trusted publisher for `portr-ai` must exist before release-please's first release of it publishes.
- To revisit: the grantr dependency, added with `portr.oauth`, and the extras as each module lands.
