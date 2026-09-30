# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
