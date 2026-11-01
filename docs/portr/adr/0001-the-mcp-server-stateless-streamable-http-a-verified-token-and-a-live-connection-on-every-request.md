# ADR-0001: The MCP server: stateless Streamable HTTP, a verified token and a live connection on every request

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Decisions P5 and P6, and the gateway's first part (#917); lattice [ADR-0044](../../adr/0044-tenant-wide-commands-called-with-no-workspace-and-checked-on-the-tenant.md) for the workspace

## Context

portr serves lattice's commands to outside clients such as Claude. RFC-0014 decides:

- **The transport (P5):** MCP 2026-07-28 first, which is stateless.
- **The token's audience (P6):** Supabase's access token hook sets `aud` to the gateway's URI, and every call checks a live connection, so a portalr session's token is never accepted.
- **Registration (P9):** clients register with Supabase Auth by Dynamic Client Registration.

The owner decided on 2026-11-01 that a client names the workspace of each workspace-scoped call as an argument, and that tenant-wide commands are called with none (lattice ADR-0044). portr's core already makes, from the composed commands, the tools a connection's toolsets are offered (lattice ADR-0043). The MCP SDK, 2.2, serves a low-level `Server` over Streamable HTTP, statelessly, behind bearer authentication. It also serves the protected resource metadata of RFC 9728.

## Decision

- **`portr.mcp.PortrMcp(enforcer, commands, connections, *, portal=None)`**, behind the `mcp` extra (`mcp>=2.2`, `starlette>=0.27`), serves `tools/list` and `tools/call` on the SDK's low-level `Server`.
- **`http_app(auth=, token_verifier=)`** is the SDK's Streamable HTTP app with `stateless_http=True`: no session and no `Mcp-Session-Id`.
  - **401 and metadata:** a request without a valid token gets 401, with `WWW-Authenticate` naming the protected resource metadata, which portr serves for `auth.resource_server_url` with `auth.issuer_url` as its one authorization server.
  - **DNS rebinding protection** accepts that URL's host alone, unless the application passes its own `transport_security`. The SDK's default is localhost only, which would refuse every request a deployment gets.
- **Tokens are verified by the application's `TokenVerifier`.** With `validate_token_resource`, the SDK accepts only a token whose resource, its `aud`, is the gateway's URL (P6's first defence). Supabase's verifier, against its JWKS, comes with `portr.oauth`.
- **Every request reads its connection** through `Connections`, a port: from the verified `AccessToken`, the live `Connected` it names, or None, which refuses the request (P6's second defence). So a revoked connection stops the next call, and a token naming no connection, such as a portalr session's, is refused. An application binds it to grantr's `live` (grantr ADR-0043), so portr needs no grantr dependency yet. `Connected` holds:
  - the connection's id;
  - its one tenant;
  - the person;
  - the client's name;
  - its toolsets.
- **A client is offered its connection's toolsets,** `core` always among them, and can call only what it is offered. Any other tool name is `INVALID_PARAMS`.
- **The workspace is an argument:** every workspace-scoped tool's schema gains `workspace`, a required string, which portr removes from the arguments and puts in the call's `Scope`. A tenant-wide tool gains none and is called with no workspace. A workspace tool called without one is the tool's error, and nothing is called.
- **Every call goes through lattice-core's enforcer,** with a `CallContext` made from the connection:
  - the caller is the person (`PersonCaller`);
  - the client is `via` (the connection's id, the client's name, surface `mcp`);
  - the surface is `mcp`;
  - the correlation id is new for each call;
  - the taint is clean. The client's own context is outside lattice, and a stateless server keeps none across calls.
- **Answers:**
  - **A result** is text, with JSON as text and as structured content. With `portal`, a second block links portalr's route, its placeholders filled from the tenant, the workspace and the arguments, and cut before the first segment they can't fill.
  - **A refusal or a provider's failure** is the tool's error, with its message.
  - **A call that waits for an approval** answers its id as structured content, and, with `portal`, its page. Answering it by elicitation comes with #918.

## Options considered

### Option A: A low-level server over portr's core, every call through the enforcer (chosen)

**Pros:** what a client is offered is portr's core's, so the consent page, the docs and the server agree. The SDK serves the transport, the bearer challenge and the metadata, and portr adds nothing it would have to keep in step with the specification.
**Cons:** portr builds MCP's tool objects from its own. The SDK's high-level server would have built them from functions.

### Option B: The SDK's high-level server, a function per tool

**Cons:** the tools are composed at run time from every package's catalog, so they can't be functions declared in portr. A function per tool would bypass the enforcer, or wrap it once per tool.

### Option C: Sessions, the 2025-11-25 revision

**Cons:** P5 decides otherwise. Every piece of state across calls is a handle lattice mints, so a session would hold nothing the client doesn't pass back.

## Consequences

- Easier: an application mounts `http_app` beside its own, binds `Connections` to grantr, and gives the registry its bound providers, such as artifactr's catalog provider (artifactr ADR-0103).
- Harder: the application supplies the token verifier until `portr.oauth` brings Supabase's, and its access token hook must set `aud`.
- To come:
  - `portr.oauth`, Supabase's verifier and the consent API, where P9's registration is the authorization server's;
  - keys as a second scheme;
  - resources and `subscriptions/listen`;
  - the elicitation surface (#918);
  - limits per connection;
  - the tier ceiling `tiers:portr`, which the enforcer applies to agents' runs today and not yet to a person's call through a client.
