# ADR-0065: An access token redacted from the spans' URLs

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland
**Amends:** [lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md)'s "The token stays out of logs": the spans' half moves from the template to the libraries

## Context

A browser can't set headers as it opens a WebSocket, so the template's applications, and portalr's client, put a person's token in the `access_token` query parameter ([lattice #78](https://github.com/alexnodeland/lattice/issues/78)). FastAPI's instrumentation records each request's URL on its span: `url.query` under the current semantic conventions, `http.url` under the older ones. Tempo is shared across tenants, so anyone who reads traces could read the token there.

Lattice RFC-0002 has the template redact it. A span processor can't: the ASGI instrumentation sets the URL attributes again after the span starts, and an ended span can't be changed. Its `server_request_hook` runs after them, but neither `TelemetryHandle.instrument_app` nor `configure_telemetry`'s own instrumentation, which patches FastAPI for applications built after it, passed one.

## Decision

- **The libraries' FastAPI instrumentation always redacts `access_token`'s value from the URL attributes,** through `server_request_hook`: `instrument_app`'s, and `configure_telemetry`'s for applications built after it. It covers `url.query` and `http.url`, which FastAPI's spans set under the current and the older conventions, `http.target`, and `url.full`, which they don't set but another server span might. Only an attribute that changes is set again.
- **A parameter is `access_token` however its name is encoded,** as Starlette decodes it, so `access%5Ftoken` is redacted too, and every other parameter is kept byte for byte.
- **`access_token` is OAuth's own name** for a bearer token in a URI ([RFC 6750, section 2.3](https://www.rfc-editor.org/rfc/rfc6750#section-2.3)), so hiding it is safe in any application, not only the template's. No option turns it off.
- **`redact_access_token(text)` and `URL_ATTRIBUTES` are public,** so an application redacts its own logs the same way. The template redacts uvicorn's access log, and its log of WebSockets, with it, as RFC-0002 has it.
- **The code is the same in reflexr and artifactr** ([artifactr ADR-0068](../../artifactr/adr/0068-an-access-token-redacted-from-span-urls.md)), copied as the rest of their telemetry setup is. One home for what the packages share is [lattice #73](https://github.com/alexnodeland/lattice/issues/73).

## Options considered

| Option | For | Against |
|---|---|---|
| **The libraries redact it, always (chosen)** | Every application gets it, with nothing to pass | Moves the spans' half of RFC-0002's sentence out of the template |
| `instrument_app(app, server_request_hook=...)`, with the template's hook | RFC-0002 as written | A public parameter, which each application must know to pass |
| The template wraps the span exporter | No library change | The template builds the OTLP exporter itself, apart from the libraries' settings |
| The template instruments FastAPI itself | No library change | Bypasses the libraries' excluded spans and their shutdown |

## Consequences

- Easier: no application records a token passed in a URL on its spans, however it was built.
- Harder: an application that wants the token on its spans can't have it.
