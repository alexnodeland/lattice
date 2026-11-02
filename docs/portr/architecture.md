# Architecture

portr is lattice's gateway for outside clients ([lattice RFC-0014](../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)). It is built in phases: this page describes what is built, and grows with each phase.

## Layers

| Module | What | Imports |
|---|---|---|
| `portr.core` | What a client is offered, from the composed commands: tools, resource templates and toolsets. No I/O, no MCP SDK | pydantic, lattice-core's `capabilities` and `commands` |
| `portr.mcp` (the `mcp` extra) | The MCP server: the core's offer over stateless Streamable HTTP, behind bearer authentication, each call through lattice-core's enforcer ([ADR-0001](adr/0001-the-mcp-server-stateless-streamable-http-a-verified-token-and-a-live-connection-on-every-request.md)) | the core; the `mcp` SDK and Starlette; lattice-core's `capabilities`, `commands`, `enforcement` and `taint` |

To come, as RFC-0014 plans them: `portr.oauth`, token verification against Supabase Auth and the consent API; the elicitation surface, in `portr.mcp`; and `portr.acp`, the ACP permission surface for coding agents. Each comes behind an extra.

## What a client is offered

`offered(commands, toolsets=)` takes every command of the composed catalogs, as the registry lists them, and the toolsets a connection may use:

- **A command is offered** when it is exposed (a tool, a resource or both, never `NotExposed`), offered on the `mcp` surface, and in one of the toolsets. `core` is always among them.
- **A tool** is named by its command's tool name, `<package>_<name>`, with its command's description and input schema, its toolset, and portalr's route that a result links to.
- **Its annotations** are hints for the client, never decisions: `readOnlyHint` and `idempotentHint` for a read, `destructiveHint` for an irreversible change, and `openWorldHint` for one that sends data out or reads untrusted content. The enforcer decides every call.
- **A read exposed as a resource** is a template, by the URI its command names.

`tiers(commands)` gives each toolset's tiers, among the commands offered on `mcp`, in lattice-core's order of toolsets, for the consent page to show beside each toolset a person may let a client use.

## The MCP server

`PortrMcp(enforcer, commands, connections, *, portal=None)` serves `tools/list` and `tools/call` ([ADR-0001](adr/0001-the-mcp-server-stateless-streamable-http-a-verified-token-and-a-live-connection-on-every-request.md), lattice RFC-0014's P5 and P6). `http_app(auth=, token_verifier=)` is the MCP SDK's Streamable HTTP app, stateless.

- **Before a request reaches portr,** the SDK's bearer middleware verifies its token with the application's `TokenVerifier`, and, with `validate_token_resource`, accepts only a token issued for the gateway's URL. A request without one gets 401, naming the protected resource metadata portr serves at `/.well-known/oauth-protected-resource`, with `auth.issuer_url` as its authorization server. DNS rebinding protection accepts the resource URL's host alone.
- **Every request reads its connection:** `Connections` turns the verified token into the live `Connected` it names (its id, tenant, person, client name and toolsets), or None, which refuses the request. An application binds it to grantr's connections, so a revoked one stops the next call.
- **A client is offered its connection's toolsets**, `core` among them, as `offered` makes them, and calls only what it is offered.
- **A workspace-scoped tool takes `workspace`,** required, which portr moves into the call's scope; a tenant-wide one, such as `artifactr_list_workspaces`, takes none and is called with no workspace ([lattice ADR-0044](../adr/0044-tenant-wide-commands-called-with-no-workspace-and-checked-on-the-tenant.md)).
- **Every call goes through the enforcer** as the person, `via` the client, from surface `mcp`, clean of taint, with a correlation id of its own. A result is text and, for JSON, structured content, with a link to portalr's route when `portal` is given. A refusal or a provider's failure is the tool's error. A call that waits for an approval answers its id and its page in portalr.

## Independence

portr imports no library. Its layering test fails on an import of artifactr, reflexr, evalr, relayr or portalr, and lists what each layer may import. A library's commands reach portr only through lattice-core's registry ([lattice ADR-0043](../adr/0043-portr-a-package-of-its-own-on-lattice-core-reaching-commands-only-through-the-registry.md)).
