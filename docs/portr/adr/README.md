# Architecture decision records

Each record captures one decision: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. portr's design is [lattice RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md), and where portr lives is [lattice ADR-0043](../../adr/0043-portr-a-package-of-its-own-on-lattice-core-reaching-commands-only-through-the-registry.md).

| ADR | Title | Status |
|---|---|---|
| [0001](0001-the-mcp-server-stateless-streamable-http-a-verified-token-and-a-live-connection-on-every-request.md) | The MCP server: stateless Streamable HTTP, a verified token and a live connection on every request | Accepted |

To add a record, copy lattice's [ADR template](../../adr/template.md) to the next number and add a row above.
