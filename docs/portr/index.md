---
title: portr
description: One gateway that serves lattice's commands to outside clients over MCP and ACP, each call through the enforcer.
---

# portr

One gateway, per deployment, that serves all of lattice to outside clients: Claude Desktop, claude.ai, ChatGPT, Cursor, Zed and terminals over MCP, and coding agents over ACP ([lattice RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md), [#914](https://github.com/alexnodeland/lattice/issues/914)). Every action a person can take in portalr is a **command**, declared once by the package that owns it ([lattice ADR-0041](../adr/0041-the-command-declaration-a-capability-with-its-toolset-exposure-route-and-surfaces-in-a-static-catalog.md)), and portr offers each as a tool or a resource and calls it through lattice-core's enforcer. A client acting for a person does only what that person may, and asks them whatever they would be asked.

!!! note "Being built"

    portr's first release holds `portr.core`, which makes what a client is offered. The MCP server on Streamable HTTP, OAuth with Supabase Auth, connections, limits per connection, and approvals by elicitation follow ([#917](https://github.com/alexnodeland/lattice/issues/917), [#918](https://github.com/alexnodeland/lattice/issues/918)).

## What it holds

| Module | What |
|---|---|
| [`portr.core`](reference.md#portrcore) | `offered(commands, toolsets=)`: the tools and resource templates a connection with those toolsets is offered, `core` always among them; each tool named `<package>_<name>`, with annotations from its command's tier, reversibility and effects. `tiers(commands)`: each toolset's tiers, for the consent page |

## Where it sits

portr depends on lattice-core, and on grantr for connections, keys and audit as its OAuth module lands. It never imports artifactr, reflexr, evalr or relayr: each library's commands reach it through lattice-core's registry, from the providers the application binds at its composition root ([lattice ADR-0043](../adr/0043-portr-a-package-of-its-own-on-lattice-core-reaching-commands-only-through-the-registry.md)). Its layering test asserts it.
