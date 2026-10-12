# ADR-0015: Acceptance tests against the reference applications

**Status:** Accepted, amended by [artifactr ADR-0061](../artifactr/adr/0061-a-nul-character-is-refused-at-the-boundary.md) and [reflexr ADR-0060](../reflexr/adr/0060-a-nul-character-is-refused-at-the-boundary.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[stackr RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling)'s phase 5 adds acceptance tests:

- Each FastAPI surface's OpenAPI document, committed in its package's `schemas/` with a drift test.
- A Bruno collection per package, in `packages/<name>/bruno/`, run by its `api` task (D5).
- An Acceptance job that starts docplan, oncall and the console, runs `:api` and `:bdd`, and runs Schemathesis over the documents.

The RFC also has the `api` tasks depend on docplan's and oncall's `image` tasks, since the collections run against those applications. Phase 6 deferred Schemathesis to this phase, which has the started applications it needs.

The rehearsal left gaps:

- **The `image` tasks stop what they start.** Each builds its application, starts it with `docker compose up --wait`, and runs `docker compose down --volumes`. A job that started docplan, then ran `artifactr:api` with an `image` dependency, would have it stopped under the collection, since both use the same compose project.
- **CI runs `scripts/affected.py`, not `moon ci`.** It finds the affected projects, by their files and their tasks' inputs, and their dependents ([ADR-0002](0002-ci-runs-every-affected-project-and-its-dependents.md)). artifactr doesn't depend on docplan, so a change to docplan alone reaches `artifactr:api` only through an input.
- **The RFC fixes no prefix.** docplan and oncall mount their routers at `/v1`, the template at `/artifactr/v1` and `/reflexr/v1`, and grantr's document mounts its router at `/grantr/v1`.
- **The applications' agents need a model.** CI has no provider keys.

## Decision

- **Each library's `api` task starts its own application.**
  - The tag's task, in `.moon/tasks/api.yml`, runs `scripts/api SERVICE` from the package's directory.
  - The script starts the service from the package's `compose.yaml`, and runs the Bruno collection, then Schemathesis over the committed document.
  - It stops the service however they end, printing its logs if anything failed, and Schemathesis writes a JUnit report, which the job uploads when it fails.
  - Each run is a compose project of its own (`<package>-api`), cleared before it starts, on host ports the system picks, which the script reads back with `docker compose port`. So the two libraries' tasks run side by side, and beside the `image` tasks, with no mutex.
  - artifactr's runs against docplan and reflexr's against oncall. Each `moon.yml` names its service and adds `/examples/<app>/**/*` to the task's inputs, so a change to the application runs the library's acceptance tests. The root's `pyproject.toml` and `uv.lock` are inputs of every Python project's tasks already.
- **The Acceptance job runs `scripts/affected.py api`,** after `bun install`. It starts nothing itself, and the script installs Schemathesis with `uv run --group acceptance` only when it runs, so a pull request that affects no library with an `api` tag costs a checkout, a Bun install and moon's query. `:bdd` joins it with portalr's collection, and the console starts in portalr's own task.
- **The applications' agents run on pydantic-ai's test model.** The task sets `DOCPLAN_MODEL` and `ONCALL_MODEL` to `test`, which their compose files pass through. No provider is called, so a message still starts a run.
- **The documents are the routers' own.**
  - A bare application mounts each router at the root, and admits no one: `artifactr.fastapi.openapi` and `reflexr.fastapi.openapi`.
  - `moon run <package>:schema` writes `schemas/<package>.openapi.json`, beside the JSON Schemas, and `tests/test_openapi.py` holds it to the router, as grantr's test does.
  - Applications mount the routers where they choose, so Schemathesis's `--url` carries the prefix: docplan's and oncall's `/v1`.
  - artifactr's `fastapi` layer may now import pydantic-ai, for the runner of its bare application, whose agent never runs.
- **The collections follow one shape.**
  - `bruno.json` and `collection.bru` (with the `x-user` header the demo applications trust) sit beside one environment named after the application.
  - Requests are numbered kebab-case files. Each makes its assertions in a `tests` block.
  - The ids are fixed, since the application starts empty each time.
  - The collections cover each surface's reads, commands and rejections, rather than every case, which the libraries' own tests cover.
- **Schemathesis is the root's `acceptance` dependency group,** run with `uv run --locked --group acceptance`, and configured in the root's `schemathesis.toml`. It fails on a server error, and on every check that file doesn't turn off:
  - `status_code_conformance` and `response_schema_conformance`, everywhere, until the routers document their rejections ([#66](https://github.com/alexnodeland/lattice/issues/66)).
  - `positive_data_acceptance`, for the commands and reflexr's events only: a `type` with a default isn't required by the document, but the discriminator requires it (#66).
  - `negative_data_rejection`, for the reads that take string ids in their query only: a value Schemathesis means as a boolean, such as `true`, is a valid string id.
  - `allow_header_conformance`, for good: Starlette's 405 names only the first matching route's methods.
  - It generates no NUL bytes. The libraries refuse one in any string as `validation_failed` ([#67](https://github.com/alexnodeland/lattice/issues/67)), which the document can't say of every string, so a NUL would fail `positive_data_acceptance`.
  - The "errored" cases its summary can count are stateful steps it generated and never sent, such as a link that would leave a path parameter empty: they have no response to check, and aren't failures.
- **What the acceptance tests found and this change fixes:**
  - reflexr answered 500 to a negative `limit` on its run listing.
  - Both libraries answered 500 to a `seq` or a count past PostgreSQL's `bigint` in a read of the log. Each workspace refuses one now (`validation_failed`), and the routers' queries state the bounds, `0` to `MAX_COUNT`, in their documents.
  - Six routes answered 500, not 403, to a read `authorize` refuses, since they didn't turn a rejection into its status: artifactr's artifact, thread and proposal listings, and reflexr's rule statuses, dead letters and schedule statuses. The matrix tests now refuse every action but opening, and expect 403 from every route.
- **The Bruno CLI is a root dev tool,** at an exact version, run as `bun x --bun --no-install bru`, as every tool in the Bun workspace runs ([portalr ADR-0008](../portalr/adr/0008-the-bun-workspace-runs-in-bun.md)). `--bun` is load-bearing: the CLI starts with `#!/usr/bin/env node`, and CI has no Node.js. knip can't see it called from a shell script, so `knip.json` names it in `ignoreDependencies`.
- **The root's `overrides` hold the Bruno CLI's dependencies at fixed versions.** Its dependency tree brought seven packages with advisories that have fixes: axios, form-data, js-yaml and yaml within their majors, and @faker-js/faker 10, csv-parse 7 and uuid 11 a major up. osv-scanner then finds nothing new in `bun.lock`. The collections pass with all seven, but they exercise none of the three a major up: they use no generated data (faker), CSV iteration (csv-parse) or UUIDs of the CLI's own (uuid), so a break in those paths would show only where the CLI uses them. Bun's `overrides` are workspace-wide, so the web packages get the same versions if they ever depend on these. Drop each override once the CLI's own ranges reach it.

## Options considered

| Option | For | Against |
|---|---|---|
| **The `api` task starts and stops its application (chosen)** | Runs alike in CI and locally, with one command; nothing to start when nothing is affected; isolated, so both run at once | Builds the image again where the Images job also builds it |
| The job starts the applications, and `api` depends on `image` | As the RFC wrote it | `image` stops the application the job started; the job starts both whatever changed |
| The job starts the applications, and `api` has no dependency | No double build | A local run needs the applications started by hand, and the job always pays for both |

Schemathesis:

| Option | For | Against |
|---|---|---|
| **Every check but those recorded, per operation where a gap is, with the gaps tracked (chosen)** | Catches server errors now; the off checks are listed, each with its reason and scope | The documents' gaps stay until #66 |
| Every check | The full contract | Fails today on every route's undocumented rejections |
| `not_a_server_error` alone | Simplest | Drops checks that pass, such as content types, headers and authentication |

## Consequences

- Easier: `moon run artifactr:api` checks the REST surface end to end against a real application on PostgreSQL, as CI does.
- Easier: a change to a router that changes its document fails the drift test until the document is regenerated, and the change shows in review.
- Harder: the Acceptance job builds docplan's and oncall's images when either library or application changes, as the Images job does.
- Revisit: the excluded checks, when #66 and #67 are fixed, and portalr's collection, `bdd` task and the console, with the portal.

## Action items

1. [x] The OpenAPI documents and their drift tests.
2. [x] The Bruno collections, the `api` tasks and the Acceptance job.
3. [x] Schemathesis, with what it found fixed or recorded.
4. [ ] The rejections documented ([#66](https://github.com/alexnodeland/lattice/issues/66)), and NUL bytes refused (done: [#67](https://github.com/alexnodeland/lattice/issues/67)).
