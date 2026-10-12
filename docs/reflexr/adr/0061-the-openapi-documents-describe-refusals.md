# ADR-0061: The OpenAPI documents describe refusals

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Schemathesis found that reflexr's router answers statuses and bodies its OpenAPI document doesn't describe ([lattice #66](https://github.com/alexnodeland/lattice/issues/66)), so the Acceptance job ran with `status_code_conformance` and `response_schema_conformance` off ([lattice ADR-0015](../../adr/0015-acceptance-tests-against-the-reference-applications.md)):

- **Refusals were undocumented.** Every route can answer a rejection with `{"detail": {"type": ..., "message": ...}}`, the resolver's 401 or its own `HTTPException` with a string `detail`, or FastAPI's 422 with a list of field errors. The document listed 200 and FastAPI's 422 only, whose body differs from a rejection's.
- **Tags weren't required.** A union member's tag (`type` or `kind`) has a default, so Pydantic's schema calls it optional, though the discriminator needs it. A command without one matched the document and was refused. And a published event's `type` had no pattern in the document, so a name the server can't parse matched it.
- **An empty id in a path** (`.../runs/`) reached the list route instead, by FastAPI's slash redirect, and answered a list where the document said one item.

## Decision

- **Every route documents its refusals.** The router is built with `responses=REFUSALS`: 400, 401, 403, 404, 409 and 422, each answering `Refused`, whose `detail` is a `RejectionDetail` (`type`, `message` and the rejection's typed details), a string, or a list of `FieldError`s. `POST .../commands` answers a `CommandResult` or a `Refused` at each rejection's status. Each is described in words of its own, since FastAPI's default description, Python's phrase for the status, changed in 3.13 (`Unprocessable Content`). The models are shared verbatim with artifactr's router.
- **Every protocol model's tags are required in its JSON Schema.** `tag_required`, in `reflexr.core.tagged` and shared verbatim with artifactr, marks a model's fields fixed to one value required. Every frame, command, outcome, event, envelope, actor, target and union member names it in its config, so the committed protocol schemas and the OpenAPI document say what every frame on the wire carries, and portalr's client no longer adds it ([lattice #82](https://github.com/alexnodeland/lattice/issues/82)). A test holds the OpenAPI document and every `*.v1.json` schema to it. The document asks a REST body for its `type` too, as the WebSocket does; the server still fills it in when it is left out.
- **An event's `type` carries the event name's pattern** in the document, as `EventName` does, so Schemathesis publishes names the server can parse.
- **A path's ids are never empty** (`minLength: 1`).
- **Schemathesis checks conformance.** The root's `schemathesis.toml` turns `status_code_conformance` and `response_schema_conformance` on. `positive_data_acceptance` stays off for the commands, which can be well formed and still not apply, and for the log's reads, whose `limit` and `last` exclude each other.

## Options considered

| Option | Against |
|---|---|
| **One refusal model, a union of what `detail` can be (chosen)** | A client tells the three forms apart by shape |
| A model per status | Most statuses answer more than one form: a 403 is a rejection, or a resolver's own refusal |
| Leave FastAPI's `HTTPValidationError` at 422 | A rejection's 422 doesn't match it, so the check stays off |
| Mark tags required by rewriting the document | The application's own `/openapi.json` would still say they are optional |

## Consequences

- Easier: a client generated from the document knows every refusal's body, and Schemathesis checks every status and body.
- Harder: a new protocol model names `tag_required` in its config, or the documents' test fails.
