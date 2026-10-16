# ADR-0021: The refusal schema needs no extra

**Status:** Accepted
**Date:** 2026-10-15
**Deciders:** Alex Nodeland
**Amends:** [ADR-0018](0018-lattice-core-what-the-libraries-share.md): its fourth step, which put the routers' refusal schema in `lattice_core.fastapi` behind a `fastapi` extra

## Context

ADR-0018's fourth step moves the REST routers' refusal schema, `RejectionDetail`, `FieldError`, `Refused` and `REFUSALS`, into lattice-core. artifactr and reflexr keep it word for word, marked "shared verbatim … change both". portalr has a third copy, whose docstrings differ and whose `REFUSALS` documents four statuses where the libraries' document six: no portalr route answers 404 or 409. The names are the OpenAPI documents' component names, so a client generated from one document reads a refusal from any of them ([artifactr ADR-0063](../artifactr/adr/0063-the-openapi-documents-describe-refusals.md), [reflexr ADR-0061](../reflexr/adr/0061-the-openapi-documents-describe-refusals.md)).

The copies import pydantic and nothing else. FastAPI sees them only when a router passes `REFUSALS` to `APIRouter(responses=...)`, which is a plain dictionary.

relayr has a `Refused` of its own, an exception of its outbound actions, which is not this schema and stays.

## Decision

- **The schema is `lattice_core.refusals`, and needs no extra.** It imports pydantic alone, so the `fastapi` extra and the name `lattice_core.fastapi` ADR-0018 planned would gate and name a dependency it doesn't have. A package that serves REST depends on FastAPI itself; portalr needs lattice-core with no extra.
- **`refusals(*statuses)` builds the responses to document,** and lattice-core ships no list of statuses. Each router defines its own `REFUSALS`: artifactr and reflexr `refusals(400, 401, 403, 404, 409, 422)`, the six their routes answer, and portalr `refusals(400, 401, 403, 422)`. A router documents only what it answers.
- **`lattice_core.fastapi` stays free** for a later helper that depends on FastAPI, behind a real `fastapi` extra. [ADR-0020](0020-the-telemetry-contract-needs-no-extra.md) is the precedent for a contract that needs no extra, beside the code that does.
- **The docstrings name no package,** since they are the OpenAPI components' descriptions. The three documents' descriptions for these components are now the same words, and the generated TypeScript client is regenerated from them.
- **Each package keeps its public API.** No name is public in a package's `__init__`; a package's tests and routers import the schema from lattice-core.

## Options considered

| Option | For | Against |
|---|---|---|
| **A base module, `lattice_core.refusals` (chosen)** | No extra to install or gate; portalr depends on lattice-core as it is | ADR-0018's name and extra change |
| `lattice_core.fastapi` behind a `fastapi` extra, as planned | As ADR-0018 says | The extra would install nothing the module imports |
| One `REFUSALS` in lattice-core for every router | No builder | portalr would document 404 and 409 it never answers, and its committed document would change; and a list of statuses is a router's own |
| Leave portalr's copy | Nothing moves | A third copy to keep in step, which ADR-0018 exists to end |

## Consequences

- Easier: a change to the refused body or its documented statuses is made once, and the three documents follow.
- Easier: portalr's router builds its documented responses from lattice-core with no extra.
- Harder: `lattice_core.refusals` is public API of lattice-core once published: it changes only by addition and deprecation.
