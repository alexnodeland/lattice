# AGENTS.md: portr

Root [AGENTS.md](../../AGENTS.md) applies; this adds what is specific to portr.

portr is the gateway that serves lattice's commands to outside clients over MCP and ACP, each call through lattice-core's enforcer ([lattice RFC-0014](../../docs/rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)). See [the architecture](../../docs/portr/architecture.md).

## Rules

- **portr imports no library:** never artifactr, reflexr, evalr, relayr or portalr. Commands reach it only through lattice-core's registry ([lattice ADR-0043](../../docs/adr/0043-portr-a-package-of-its-own-on-lattice-core-reaching-commands-only-through-the-registry.md)); `tests/test_layering.py` fails otherwise.
- **`portr.core` does no I/O** and imports no MCP SDK: what a client is offered is a pure function of the commands.
- **Every call goes through the enforcer.** No module calls a provider directly.

## Commands

```bash
moon run portr:test           # pytest with the 100% branch-coverage gate
moon run portr:check          # lint, types and tests, as CI runs them
```
