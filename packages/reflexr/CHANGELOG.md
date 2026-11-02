# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0](https://github.com/alexnodeland/lattice/compare/reflexr-v0.5.0...reflexr-v0.6.0) (2026-11-02)


### ⚠ BREAKING CHANGES

* **core:** `lattice_core.capabilities.Scope.workspace_id` is `str | None`, and `Integrations.is_enabled`, `Settings.value` and grantr's `Holds` take a workspace that may be None. An application's own implementation of one of them, or its own `Provider`, must accept None, which a tenant-wide command's call passes.

### Features

* **core:** tenant-wide commands, called with no workspace and checked on the tenant (ADR-0044) ([#1382](https://github.com/alexnodeland/lattice/issues/1382)) ([97c80a5](https://github.com/alexnodeland/lattice/commit/97c80a5ebe70cbe0bf86c2bb4b709f66d035fdf8))

## [0.5.0](https://github.com/alexnodeland/lattice/compare/reflexr-v0.4.0...reflexr-v0.5.0) (2026-11-01)


### Features

* **core:** parity: every operation names its command, and one test holds the catalogs to grantr (RFC-0014 P13) ([#1366](https://github.com/alexnodeland/lattice/issues/1366)) ([0138269](https://github.com/alexnodeland/lattice/commit/013826911c9cb515ef3c45ad49c0afb396f876de))

## [0.4.0](https://github.com/alexnodeland/lattice/compare/reflexr-v0.3.0...reflexr-v0.4.0) (2026-11-01)


### Features

* **reflexr:** reflexr's provider: each call in its workspace, as its actor (RFC-0014) ([#1352](https://github.com/alexnodeland/lattice/issues/1352)) ([6298a0f](https://github.com/alexnodeland/lattice/commit/6298a0f96851b4fd4709d242a2648faaa76b0b4b))

## [0.3.0](https://github.com/alexnodeland/lattice/compare/reflexr-v0.2.2...reflexr-v0.3.0) (2026-11-01)


### Features

* **reflexr:** reflexr's commands, every action a command or listed with its reason (RFC-0014 phase 1) ([#1340](https://github.com/alexnodeland/lattice/issues/1340)) ([0068333](https://github.com/alexnodeland/lattice/commit/00683336d1b699b2f034297cd755a336d017dacc))

## [0.2.2](https://github.com/alexnodeland/lattice/compare/reflexr-v0.2.1...reflexr-v0.2.2) (2026-11-01)


### Bug Fixes

* **core:** let an approval through only for the call that asked it ([#1283](https://github.com/alexnodeland/lattice/issues/1283)) ([713403b](https://github.com/alexnodeland/lattice/commit/713403bc3365e60c840e90a2056888089da61ae1))

## [0.2.1](https://github.com/alexnodeland/lattice/compare/reflexr-v0.2.0...reflexr-v0.2.1) (2026-10-30)


### Bug Fixes

* **stack:** name each pg-up's compose project with a random token ([#1163](https://github.com/alexnodeland/lattice/issues/1163)) ([585b868](https://github.com/alexnodeland/lattice/commit/585b8689a4cdc68475c994b32b9e3bc57a91c64e))

## [0.2.0](https://github.com/alexnodeland/lattice/compare/reflexr-v0.1.1...reflexr-v0.2.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **reflexr:** report a rule's validation errors with a structured loc ([#723](https://github.com/alexnodeland/lattice/issues/723))

### Features

* **reflexr:** report a rule's validation errors with a structured loc ([#723](https://github.com/alexnodeland/lattice/issues/723)) ([d712c87](https://github.com/alexnodeland/lattice/commit/d712c878dd4dfc4974f0b50a1fe9b59ae531aed6))

## [0.1.1](https://github.com/alexnodeland/lattice/compare/reflexr-v0.1.0...reflexr-v0.1.1) (2026-10-17)


### Bug Fixes

* **deps:** raise the floors on sibling packages to their released versions ([#333](https://github.com/alexnodeland/lattice/issues/333)) ([54ff956](https://github.com/alexnodeland/lattice/commit/54ff9566b418ab8bcbdb797385c2dc0b6e0a10e5))

## 0.1.0 (2026-10-17)


### ⚠ BREAKING CHANGES

* **reflexr:** `Storage` has a new method, `rule_history`, which a storage implemented outside reflexr must add. Migration 0008 adds a column and a partial index to `reflexr_events`, holding the table while it runs. relayr's `INSTALLS_READ` is removed.

### Features

* acceptance tests, with Bruno and Schemathesis against docplan and oncall ([#68](https://github.com/alexnodeland/lattice/issues/68)) ([64ad30e](https://github.com/alexnodeland/lattice/commit/64ad30ef509cd324dc5593d8b0051d0094d30958))
* **artifactr,reflexr:** LiteLLM requests carry the trace tags Langfuse propagates ([#203](https://github.com/alexnodeland/lattice/issues/203)) ([f8423ca](https://github.com/alexnodeland/lattice/commit/f8423ca118385eb81d7a33b0ea405970c7cb05da))
* **grantr:** SQL storage, the admin API, and telemetry ([#60](https://github.com/alexnodeland/lattice/issues/60)) ([d75c4f7](https://github.com/alexnodeland/lattice/commit/d75c4f796ecb0ea2c87a3084a8e6ed1e1d342f11))
* **lattice-core:** a tenant-workspace tag on every LiteLLM request, so spend reads per tenant's workspace ([#190](https://github.com/alexnodeland/lattice/issues/190)) ([95ffe96](https://github.com/alexnodeland/lattice/commit/95ffe9641ecce3797dcfa6dd2276cdcb08d00920))
* **lattice-core:** one package for what the libraries share, starting with tag_required and the NUL check ([#175](https://github.com/alexnodeland/lattice/issues/175)) ([e3074fc](https://github.com/alexnodeland/lattice/commit/e3074fc6afd9e362f263dc8964fe386e8fa65efa))
* **lattice-core:** the OpenTelemetry setup, Langfuse's span filters, the LiteLLM model and the logging guard ([#187](https://github.com/alexnodeland/lattice/issues/187)) ([508d276](https://github.com/alexnodeland/lattice/commit/508d2761b583837e2aeb99880e930a75ed4c32c3))
* **lattice-core:** the routers' refusal schema, shared by artifactr, reflexr and portalr ([#200](https://github.com/alexnodeland/lattice/issues/200)) ([1b335b1](https://github.com/alexnodeland/lattice/commit/1b335b1320d8d6ec14a185e4911e9c0c94dac221))
* **lattice-core:** the SQL helpers the libraries' storages share, behind a sql extra ([#186](https://github.com/alexnodeland/lattice/issues/186)) ([9b6a571](https://github.com/alexnodeland/lattice/commit/9b6a57144d9efdfd933d66b80a86a87ce7e10a8c))
* **reflexr:** a stored rule's history, read by its name, so relayr finds its installs however far back ([#151](https://github.com/alexnodeland/lattice/issues/151)) ([66e096a](https://github.com/alexnodeland/lattice/commit/66e096aff95e3eabe25a5c02603fb0c7cff8616c))
* **reflexr:** ExternalAgentActor gains on_behalf_of ([#74](https://github.com/alexnodeland/lattice/issues/74)) ([dca9e52](https://github.com/alexnodeland/lattice/commit/dca9e52f226fb1008914d5c9d5d579632512331b))
* **reflexr:** reserved publishers, the actors that alone may publish a type ([#72](https://github.com/alexnodeland/lattice/issues/72)) ([dd51dd4](https://github.com/alexnodeland/lattice/commit/dd51dd4d71e44c9fd7b632b5787a8803a3f58139)), closes [#8](https://github.com/alexnodeland/lattice/issues/8)
* **reflexr:** row-level security in the SQL adapter, with the scheduler's reads on the owner's engine ([#102](https://github.com/alexnodeland/lattice/issues/102)) ([4cb71dd](https://github.com/alexnodeland/lattice/commit/4cb71dd6565955fce589be41f0e0df030a1bc63f))
* **reflexr:** the protocol schema names reflexr's own events, and portalr types them ([#162](https://github.com/alexnodeland/lattice/issues/162)) ([db8bd5e](https://github.com/alexnodeland/lattice/commit/db8bd5e8814ab38c33872e52c1ff2047479c323a))
* **relayr:** row-level security in the SQL ledger, with the followers' start on the owner's engine ([#106](https://github.com/alexnodeland/lattice/issues/106)) ([437ae71](https://github.com/alexnodeland/lattice/commit/437ae71cd2432e0268a189d04cf466501967e3a1))
* **relayr:** the inbound adapter, with followers, the ledger and the bridged types ([#70](https://github.com/alexnodeland/lattice/issues/70)) ([ce51f03](https://github.com/alexnodeland/lattice/commit/ce51f03ca740b903b50c6996ae86b3ab20893c18))
* **stackr:** one tenant attribute on every signal, and prom-label-proxy for portalr ([#95](https://github.com/alexnodeland/lattice/issues/95)) ([984e309](https://github.com/alexnodeland/lattice/commit/984e3099a5a56a8bb2f6b56b13230850a53ad821))


### Bug Fixes

* a caller the resolver refuses is answered 403, or 400, on every route and stream ([#75](https://github.com/alexnodeland/lattice/issues/75)) ([1c0c66d](https://github.com/alexnodeland/lattice/commit/1c0c66da0193129611ba79d81ed1d4bd176d623f))
* a NUL character in any string is validation_failed, on every storage ([#84](https://github.com/alexnodeland/lattice/issues/84)) ([218d6a6](https://github.com/alexnodeland/lattice/commit/218d6a6fb36c2b0af4f6295664d74dd0bcfefe2f)), closes [#67](https://github.com/alexnodeland/lattice/issues/67)
* **artifactr,reflexr:** redact an access token from the spans' URLs, and the template from uvicorn's logs ([#163](https://github.com/alexnodeland/lattice/issues/163)) ([398d258](https://github.com/alexnodeland/lattice/commit/398d258c81e610c291e8433349f937bbe006d124))
* **reflexr:** an epoch fences each attempt, so a cancelled and retried one cannot record ([#247](https://github.com/alexnodeland/lattice/issues/247)) ([bc2adfe](https://github.com/alexnodeland/lattice/commit/bc2adfe496dbba06fb483c71fee57f1457e40354))
* the OpenAPI documents describe every refusal, and every tag is required ([#90](https://github.com/alexnodeland/lattice/issues/90)) ([0e09c4b](https://github.com/alexnodeland/lattice/commit/0e09c4bd7a2470b5ff0360a1e29857b5370e8106)), closes [#66](https://github.com/alexnodeland/lattice/issues/66) [#82](https://github.com/alexnodeland/lattice/issues/82)
* what ty's trial found: missing [@override](https://github.com/override), context managers' types, and a callable without a name ([#62](https://github.com/alexnodeland/lattice/issues/62)) ([6bca781](https://github.com/alexnodeland/lattice/commit/6bca78150eed3fc1d9e7822206421c4f6df28313))

## [Before lattice]

### Features

- Commands carried out once per id on every surface, MCP's tools included ([#90](https://github.com/alexnodeland/reflexr/pull/90)) (**breaking**)
- Read a workspace's rule over REST and MCP, and change stored rules with MCP tools ([#89](https://github.com/alexnodeland/reflexr/pull/89))
- Stored rules installed, updated and archived in a workspace, and run by the reactor ([#88](https://github.com/alexnodeland/reflexr/pull/88)) (**breaking**)
- Storage for stored rules, in memory and in SQL, with migration 0006 ([#87](https://github.com/alexnodeland/reflexr/pull/87)) (**breaking**)
- Typed params for actions, and core's configuration and checks for stored rules ([#86](https://github.com/alexnodeland/reflexr/pull/86)) (**breaking**)
- Qualify every event type and rule name with its namespace ([#83](https://github.com/alexnodeland/reflexr/pull/83)) (**breaking**)
- **otel**: Telemetry that composes with artifactr's, untraced polling and mirror cursors ([#76](https://github.com/alexnodeland/reflexr/pull/76)) (**breaking**)
- **workspace**: A graceful stop for Reactor.serve ([#69](https://github.com/alexnodeland/reflexr/pull/69))
- **scores**: Build the mirror on evalr's score mapping and ports ([#70](https://github.com/alexnodeland/reflexr/pull/70))
- **litellm**: Litellm_model takes model settings, as pydantic-ai models do ([#68](https://github.com/alexnodeland/reflexr/pull/68))
- **protocol**: Read a window, types and the tail of the log, and join at its head ([#67](https://github.com/alexnodeland/reflexr/pull/67))
- **agent**: Infer decisions' and forks' input types for graph checkpoints ([#52](https://github.com/alexnodeland/reflexr/pull/52))
- **deploy**: Grafana dashboards, tested against the metric registry ([#51](https://github.com/alexnodeland/reflexr/pull/51))
- **oncall**: Add the reference implementation, an incident-response app on the public API ([#40](https://github.com/alexnodeland/reflexr/pull/40))
- **litellm**: Route agents through a LiteLLM proxy, with guardrail blocks as permanent failures ([#42](https://github.com/alexnodeland/reflexr/pull/42))
- **workspace**: Typed run failures, recorded with a reason, permanent ones not retried ([#41](https://github.com/alexnodeland/reflexr/pull/41))
- **otel,langfuse**: Configure OpenTelemetry in one call, and file traces and feedback in Langfuse ([#39](https://github.com/alexnodeland/reflexr/pull/39))
- **evals**: Replay examples against a candidate action, as evalr experiment tasks ([#37](https://github.com/alexnodeland/reflexr/pull/37))
- **sql**: Store workspaces in PostgreSQL and SQLite, completing phase 4 ([#36](https://github.com/alexnodeland/reflexr/pull/36))
- **evals**: Measure workflows end to end from the log ([#35](https://github.com/alexnodeland/reflexr/pull/35))
- **evals**: Feedback as evalr examples, and evaluators as rules ([#34](https://github.com/alexnodeland/reflexr/pull/34))
- **workspace**: Enter a run context around each attempt, with its chain in baggage ([#33](https://github.com/alexnodeland/reflexr/pull/33))
- **scores**: Feedback as scores, a log mirror, and their ports ([#32](https://github.com/alexnodeland/reflexr/pull/32))
- **mcp**: Serve the workspace protocol to external agents over MCP ([#31](https://github.com/alexnodeland/reflexr/pull/31))
- **agent**: Run pydantic-graph graphs as actions, checkpointed at safe step boundaries ([#30](https://github.com/alexnodeland/reflexr/pull/30))
- **fastapi**: Serve the workspace protocol over REST and WebSocket ([#29](https://github.com/alexnodeland/reflexr/pull/29))
- **core**: Define the reflexr.v1 protocol, with one command handler ([#28](https://github.com/alexnodeland/reflexr/pull/28))
- **agent**: Run pydantic-ai agents as actions, with the EventContext capability ([#27](https://github.com/alexnodeland/reflexr/pull/27))
- **workspace**: Publish ticks on schedules, completing phase 2 ([#26](https://github.com/alexnodeland/reflexr/pull/26))
- **workspace**: Execute runs under leases, with the action port and Reaction ([#25](https://github.com/alexnodeland/reflexr/pull/25))
- **workspace**: Evaluate rules in the reactor, with replays and bounded depth ([#24](https://github.com/alexnodeland/reflexr/pull/24))
- **workspace**: Add the storage port, in-memory storage, workspace handles and telemetry ([#23](https://github.com/alexnodeland/reflexr/pull/23))
- **core**: Add typed feedback, evaluator actors and trace context ([#22](https://github.com/alexnodeland/reflexr/pull/22))
- **core**: Add the pure rules, conformance suite and run lifecycle ([#17](https://github.com/alexnodeland/reflexr/pull/17))

### Bug fixes

- Refuse a workspace with its rejection, over REST and MCP, as artifactr does ([#82](https://github.com/alexnodeland/reflexr/pull/82)) (**breaking**)
- Cancel-safe storage, and an executor that cancels plainly ([#79](https://github.com/alexnodeland/reflexr/pull/79)) (**breaking**)
- **agent**: Save graph checkpoints only if they read back, and start over from stale ones ([#71](https://github.com/alexnodeland/reflexr/pull/71))
- **mcp**: Leave logging as it was when building the MCP server ([#73](https://github.com/alexnodeland/reflexr/pull/73))
- **workspace**: Due runs are the runs that can start, and settling waits out other reactors ([#64](https://github.com/alexnodeland/reflexr/pull/64)) (**breaking**)
- **mcp**: Report what REST reports, and check run subscriptions ([#61](https://github.com/alexnodeland/reflexr/pull/61))
- **fastapi**: Show a tenant only its own schedule targets ([#59](https://github.com/alexnodeland/reflexr/pull/59))
- What the documentation found: disabled rules, filter checks, feedback sources, MCP authorization, chains ([#56](https://github.com/alexnodeland/reflexr/pull/56)) (**breaking**)
- **workspace**: What the oncall example found: emitted ids per checkpoint, run-only events ([#44](https://github.com/alexnodeland/reflexr/pull/44))

### Documentation

- **rfc**: RFC-0003's migration is 0006, and its rule names landed with [reflexr#45](https://github.com/alexnodeland/reflexr/issues/45) ([#84](https://github.com/alexnodeland/reflexr/pull/84))
- **rfc**: RFC-0003 managing rules at runtime ([#75](https://github.com/alexnodeland/reflexr/pull/75))
- **adr**: Namespaced event types ([#74](https://github.com/alexnodeland/reflexr/pull/74))
- Regenerate the changelog, and have the site regenerate it on every build ([#60](https://github.com/alexnodeland/reflexr/pull/60))
- Render lists on the site as GitHub does, and check them in the build ([#55](https://github.com/alexnodeland/reflexr/pull/55))
- Mark RFC-0002 Implemented, and list the docs targets in CONTRIBUTING ([#54](https://github.com/alexnodeland/reflexr/pull/54))
- The documentation site and the brand family ([#49](https://github.com/alexnodeland/reflexr/pull/49))
- **rfc**: RFC-0002 observability, feedback, evaluation and the LLM gateway ([#18](https://github.com/alexnodeland/reflexr/pull/18))
- **adr**: Give reflexr tenants and workspaces, like artifactr ([#16](https://github.com/alexnodeland/reflexr/pull/16))
- Add the reflexr design: architecture, protocol, RFC-0001 and ADRs ([#14](https://github.com/alexnodeland/reflexr/pull/14))

### Refactoring

- Scores through evalr's Langfuse adapters, on [evalr#34](https://github.com/alexnodeland/evalr/issues/34) ([#81](https://github.com/alexnodeland/reflexr/pull/81)) (**breaking**)
- Say each rule once, save nothing before a decision, and match artifactr ([#80](https://github.com/alexnodeland/reflexr/pull/80)) (**breaking**)

### Testing

- Register test event types once, with no inline suppressions anywhere ([#38](https://github.com/alexnodeland/reflexr/pull/38))

### Miscellaneous

- Build the docs once, and deploy them in order ([#85](https://github.com/alexnodeland/reflexr/pull/85))
- Build oncall's image and start it, not only validate Compose ([#66](https://github.com/alexnodeland/reflexr/pull/66))
- A contributor Compose stack and a Compose-based dev container ([#50](https://github.com/alexnodeland/reflexr/pull/50))
- Pin evalr at its v0.1, and check the feedback source against evalr's contract ([#43](https://github.com/alexnodeland/reflexr/pull/43))
- Lay the foundation for the reflexr library ([#15](https://github.com/alexnodeland/reflexr/pull/15))
