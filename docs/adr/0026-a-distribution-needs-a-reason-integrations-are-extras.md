# ADR-0026: A distribution needs a reason; integrations are extras

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

**Amends:** [ADR-0023](0023-publishing-to-pypi-from-the-release-workflow.md)'s amendment "a package added unreleased", and supersedes [native files ADR-0001](../artifactr/files/adr/0001-a-separate-distribution.md).

## Context

Three RFCs proposed a distribution each for an integration of artifactr: [RFC-0003](../rfcs/0003-native-files-as-artifacts.md) `artifactr-files-ai` for native files, [RFC-0005](../rfcs/0005-forms-dashboards-and-mini-apps.md) `artifactr-ui-ai` for forms and dashboards, and [RFC-0006](../rfcs/0006-excalidraw-diagrams-drawn-live.md) `artifactr-excalidraw-ai` for diagrams. RFC-0003's was built (#346) and never released. Each said why it was apart from artifactr: it is a domain built on artifactr, not an adapter for one of its ports ([artifactr ADR-0034](../artifactr/adr/0034-ports-and-adapters-for-integrations.md)), and it keeps its tables and dependencies out of applications that don't use it.

A distribution in lattice costs more than its code. The first release ([ADR-0023](0023-publishing-to-pypi-from-the-release-workflow.md) and its amendments) showed the price of each:

- **A pending publisher on PyPI,** of which an account may have three at a time, and each in a GitHub environment of its own, `pypi-<distribution>`, with its reviewers and tag restriction, since PyPI keeps one pending configuration to one project name.
- **A release pull request of its own,** whose line in `.release-please-manifest.json` sits next to the others', so each release that merges puts its neighbours' release pull requests in conflict with `main` until release-please opens them again.
- **A place in the publishing order,** `STAGES` in `scripts/release_plan.py`, after everything it requires, and a dispatch per release in that order.
- **Floors raised by hand** on the packages it requires, which uv can lock only once their own releases are on `main`, so a new floor waits on its sibling's release pull request.
- **Its own CI wiring:** a moon project, a database in CI and Nightly, a compose file and a port, and its entries in the README, the site and CONTRIBUTING.

An integration that ships with artifactr and is used with artifactr pays all of it for nothing its users can see. Turning one on is a choice per workspace, not per install: an application that serves many tenants installs once, and each workspace has the integrations it was given.

## Decision

- **A separate distribution needs a reason,** one of two: a dependency set the base should not pull in, which an extra can't keep out because the code that needs it is imported by default, or consumers and a release cadence of its own, such as a library other projects use without artifactr. The libraries released today each have one: evalr, reflexr, grantr and lattice-core are used without artifactr, relayr brings reflexr, which artifactr must not, and portalr serves UIs of its own. An integration of artifactr has neither.
- **Integrations are extras of the package they integrate with,** in that package's distribution, and are turned on at runtime, per workspace, by the shared Integrations switch ([RFC-0006](../rfcs/0006-excalidraw-diagrams-drawn-live.md) proposes it; it isn't built yet). The extra carries the dependencies the integration adds, and nothing else: installing it turns nothing on.
- **An integration's code is a subpackage the base never imports,** such as `artifactr.files`. `import artifactr` works without the extra, and the package's layering test holds the rest of it to importing nothing of the integration. An integration may keep its own tables, its own Alembic chain and its own version table, which ship in the wheel and run only when an application migrates them.
- **Its docs are a section of the package's,** such as `docs/artifactr/files/`, and its ADRs, if it has its own series, keep their numbers there and are named with it, as in "native files ADR-0002".
- **Native files are the first:** `artifactr-files` is now artifactr's `files` extra, `artifactr-ai[files]`, imported as `artifactr.files`. Forms and dashboards (RFC-0005) and diagrams (RFC-0006) follow as extras of `artifactr-ai`.
- **Versions stay independent** for the libraries that remain distributions. Whether they move to lockstep versioning is decided after the v0.2 round, in a record of its own.

## Options considered

### Option A: A distribution needs a reason; integrations are extras (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one more extra and a subpackage, no release wiring |
| Release ceremony | None added: the integration releases with the package |
| Install size | The base wheel carries the integration's code; its dependencies stay behind the extra |
| Coupling | The integration's floor on the package is the package itself, so none is raised by hand |

**Pros:** no pending publisher, environment, release pull request, stage or floor per integration; one version to report and to install; the integration's tests run with the package's on every change to it.
**Cons:** the package's wheel grows with each integration's code, and an integration can't release faster than its package.

### Option B: A distribution per integration (RFC-0003's D5, RFC-0005's and RFC-0006's packaging)

| Dimension | Assessment |
|---|---|
| Complexity | High: a package's configuration, release and docs, each time |
| Release ceremony | All of the context's, for each |
| Install size | The base wheel is unchanged |

**Pros:** the package's wheel and its migration chain are untouched by an integration.
**Cons:** the ceremony above, for code with no consumers of its own; three integrations alone would use every pending publisher an account may hold at once.

### Option C: Integrations in the package, with no extra

**Cons:** an install says nothing of what it uses, and an integration that adds dependencies would make every application carry them.

## Trade-off analysis

The ceremony is paid per distribution, and it buys independence that an integration doesn't use: it is released when its package is, for that package's users. An extra keeps what Option B kept out of the base, the integration's dependencies, and its own tables keep their own chain and stay empty in a database that never migrates them. What Option A gives up is a wheel without the integration's code, which is small next to what a separate distribution costs.

## Consequences

- Easier: a new integration is a subpackage, an extra and a section of the docs; nothing in release-please, `STAGES`, CI's databases or PyPI changes.
- Easier: an integration's floor on its package is gone, and its tests run with its package's, on its package's databases.
- Harder: the base package's wheel holds every integration's code, and its layering test must keep the base from importing any of it.
- Harder: an integration that needs a release before its package's next one waits for it.
- Revisit: a distribution that this rule would not admit today, if one turns up; and lockstep versioning, after the v0.2 round.

## Action items

1. [x] Fold `artifactr-files` into artifactr as the `files` extra, `artifactr.files`, and take it out of release-please, `STAGES`, CI, Nightly and moon.
2. [x] Amend RFC-0003, RFC-0005 and RFC-0006 to name the extras, with dated notes.
3. [ ] Build forms and dashboards (RFC-0005) and diagrams (RFC-0006) as extras of `artifactr-ai`.
4. [ ] The shared Integrations switch, which turns an integration on per workspace.
5. [ ] Decide lockstep versioning after the v0.2 round.
