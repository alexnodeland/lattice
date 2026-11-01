# Architecture

portr is lattice's gateway for outside clients ([lattice RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)). It is built in phases: this page describes what is built, and grows with each phase.

## Layers

| Module | What | Imports |
|---|---|---|
| `portr.core` | What a client is offered, from the composed commands: tools, resource templates and toolsets. No I/O, no MCP SDK | pydantic, lattice-core's `capabilities` and `commands` |

To come, as RFC-0014 plans them: `portr.mcp`, the Streamable HTTP server on the `mcp` SDK, with the protected resource metadata and the elicitation surface; `portr.oauth`, token verification against Supabase Auth, the connection check and the consent API; and `portr.acp`, the ACP permission surface for coding agents. Each comes behind an extra.

## What a client is offered

`offered(commands, toolsets=)` takes every command of the composed catalogs, as the registry lists them, and the toolsets a connection may use:

- **A command is offered** when it is exposed (a tool, a resource or both, never `NotExposed`), offered on the `mcp` surface, and in one of the toolsets. `core` is always among them.
- **A tool** is named by its command's tool name, `<package>_<name>`, with its command's description and input schema, its toolset, and portalr's route that a result links to.
- **Its annotations** are hints for the client, never decisions: `readOnlyHint` and `idempotentHint` for a read, `destructiveHint` for an irreversible change, and `openWorldHint` for one that sends data out or reads untrusted content. The enforcer decides every call.
- **A read exposed as a resource** is a template, by the URI its command names.

`tiers(commands)` gives each toolset's tiers, among the commands offered on `mcp`, in lattice-core's order of toolsets, for the consent page to show beside each toolset a person may let a client use.

## Independence

portr imports no library. Its layering test fails on an import of artifactr, reflexr, evalr, relayr or portalr, and lists what each layer may import. A library's commands reach portr only through lattice-core's registry ([lattice ADR-0043](../adr/0043-portr-a-package-of-its-own-on-lattice-core-reaching-commands-only-through-the-registry.md)).
