# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/alexnodeland/lattice/compare/artifactr-v0.1.0...artifactr-v0.2.0) (2026-09-30)


### ⚠ BREAKING CHANGES

* **agent:** the storage protocol's `Transaction` has a new required method, `save_cursor(name, seq)`, which a custom storage must implement: it saves a named cursor in the same transaction as the transaction's other writes. SQL storages also need migration 0005, which records the upgrade point for existing threads.

### Bug Fixes

* **agent:** take each turn from the log, so a message sent as a run ends is carried out once ([#35](https://github.com/alexnodeland/lattice/issues/35)) ([7f4c2ea](https://github.com/alexnodeland/lattice/commit/7f4c2ea53c2ee9e88bb599f11de14ddaa8363bd1))

## [Before lattice]

### Features

- Notices, messages that don't start or steer a turn ([#75](https://github.com/alexnodeland/artifactr/pull/75))
- **otel**: Telemetry that composes with reflexr's, untraced polling and mirror cursors ([#67](https://github.com/alexnodeland/artifactr/pull/67)) (**breaking**)
- **core**: A message id is used once in a workspace ([#66](https://github.com/alexnodeland/artifactr/pull/66)) (**breaking**)
- Carry the trace context on envelopes, as reflexr does ([#65](https://github.com/alexnodeland/artifactr/pull/65)) (**breaking**)
- **scores**: Build the mirror on evalr's score mapping and ports ([#59](https://github.com/alexnodeland/artifactr/pull/59))
- **mcp**: The reads REST has, and commands carried out once per id on every surface ([#56](https://github.com/alexnodeland/artifactr/pull/56)) (**breaking**)
- The rough edges stackr's template found: model settings, a streaming scripted model, a typed MCP resolver ([#57](https://github.com/alexnodeland/artifactr/pull/57))
- **protocol**: Let a client join at the head of the log, and read its tail ([#58](https://github.com/alexnodeland/artifactr/pull/58))
- **examples**: Docplan closes the evaluation loop with the [evals] extra ([#52](https://github.com/alexnodeland/artifactr/pull/52))
- **evals**: The [evals] extra over evalr ([#39](https://github.com/alexnodeland/artifactr/pull/39))
- **examples**: Docplan observed, rated and routed when configured ([#35](https://github.com/alexnodeland/artifactr/pull/35))
- **litellm**: Route agents through a LiteLLM proxy, with typed guardrail blocks ([#34](https://github.com/alexnodeland/artifactr/pull/34))
- **agent**: Typed run failures, recorded with a reason ([#33](https://github.com/alexnodeland/artifactr/pull/33))
- **deploy**: Grafana dashboards, tested against the metric registry ([#32](https://github.com/alexnodeland/artifactr/pull/32))
- **langfuse**: The Langfuse adapter for traces and feedback scores ([#30](https://github.com/alexnodeland/artifactr/pull/30))
- **scores**: Feedback as scores, a log mirror, and their ports ([#29](https://github.com/alexnodeland/artifactr/pull/29))
- **core**: Typed feedback, evaluator actors and the give_feedback command ([#28](https://github.com/alexnodeland/artifactr/pull/28))
- **otel**: Configure_telemetry, an OpenTelemetry SDK adapter ([#27](https://github.com/alexnodeland/artifactr/pull/27))
- **telemetry**: Trace turns, commits and tool calls, with a metric registry ([#26](https://github.com/alexnodeland/artifactr/pull/26))
- **core**: Record each run attempt's trace id ([#25](https://github.com/alexnodeland/artifactr/pull/25))

### Bug fixes

- **mcp**: Refuse an empty command id, and align with reflexr ([#76](https://github.com/alexnodeland/artifactr/pull/76))
- **agent**: Stop a run whose claim is lost, and drop what it records once abandoned ([#74](https://github.com/alexnodeland/artifactr/pull/74))
- **agent**: Record a run left running as abandoned when its thread is next claimed ([#72](https://github.com/alexnodeland/artifactr/pull/72))
- Cancel-safe storage, and a runner that stops its runs at shutdown ([#69](https://github.com/alexnodeland/artifactr/pull/69)) (**breaking**)
- **mcp**: Leave logging as it was when building the MCP server ([#64](https://github.com/alexnodeland/artifactr/pull/64))
- **mcp**: Ask an authorize hook before a client uses a workspace ([#47](https://github.com/alexnodeland/artifactr/pull/47))
- **sql**: Keep one connection per SQLite engine, so transactions queue in order ([#46](https://github.com/alexnodeland/artifactr/pull/46))
- **deploy**: Dashboards stackr can fetch, with rates that have data ([#44](https://github.com/alexnodeland/artifactr/pull/44))
- **otel**: Instrument httpx2 when httpx is not installed ([#37](https://github.com/alexnodeland/artifactr/pull/37))

### Documentation

- An authorize example that serves both people and MCP clients ([#48](https://github.com/alexnodeland/artifactr/pull/48))
- Regenerate the changelog, and have the site regenerate it on every build ([#45](https://github.com/alexnodeland/artifactr/pull/45))
- Render lists on the site as GitHub does, and check them in the build ([#43](https://github.com/alexnodeland/artifactr/pull/43))
- Wrap up RFC-0002: status, open questions and ADR action items ([#36](https://github.com/alexnodeland/artifactr/pull/36))
- **rfc**: RFC-0002 observability, feedback, evaluation and the LLM gateway ([#21](https://github.com/alexnodeland/artifactr/pull/21))

### Refactoring

- One Runner.execute, reads the workspace owns, scores on evalr, and parity with reflexr ([#70](https://github.com/alexnodeland/artifactr/pull/70)) (**breaking**)

### Testing

- No inline suppressions anywhere, as in reflexr ([#40](https://github.com/alexnodeland/artifactr/pull/40))

### Miscellaneous

- Build the docs once, and deploy them in order ([#71](https://github.com/alexnodeland/artifactr/pull/71))
- Build docplan's image and start it, not only validate Compose ([#55](https://github.com/alexnodeland/artifactr/pull/55))
- Hold the docs script to the library's gates, and mark RFC-0002 Implemented ([#41](https://github.com/alexnodeland/artifactr/pull/41))
- A contributor Compose stack and a Compose-based dev container ([#31](https://github.com/alexnodeland/artifactr/pull/31))

## [0.1.0] - 2026-09-28

### Features

- **examples**: Keep docplan's workspaces in a database when configured ([#15](https://github.com/alexnodeland/artifactr/pull/15))
- **sql**: Add SQLAlchemy storage and migrations ([#9](https://github.com/alexnodeland/artifactr/pull/9))
- **examples**: Add docplan, the reference implementation ([#14](https://github.com/alexnodeland/artifactr/pull/14))
- **core**: Describe a proposed edit when it is proposed ([#13](https://github.com/alexnodeland/artifactr/pull/13))
- **core**: Include an artifact's kind when a version is serialized ([#10](https://github.com/alexnodeland/artifactr/pull/10))
- **surfaces**: Add the WebSocket, REST and MCP surfaces ([#8](https://github.com/alexnodeland/artifactr/pull/8))
- **agent**: Add the pydantic-ai capability, live output and runner ([#7](https://github.com/alexnodeland/artifactr/pull/7))
- **workspace**: Add scoped workspace handles over pluggable storage ([#6](https://github.com/alexnodeland/artifactr/pull/6))
- **core**: Add the pure rules, conformance suite and host contract ([#4](https://github.com/alexnodeland/artifactr/pull/4))

### Bug fixes

- **fastapi**: Watch only live runs in the threads a client follows ([#12](https://github.com/alexnodeland/artifactr/pull/12))
- **agent**: Record the result of a tool that retries or fails on its own ([#11](https://github.com/alexnodeland/artifactr/pull/11))

### Documentation

- Publish the site at artifactr.alexnodeland.com from main ([#19](https://github.com/alexnodeland/artifactr/pull/19))
- Add the documentation site and brand ([#16](https://github.com/alexnodeland/artifactr/pull/16))
- Add architecture, thread protocol and ADRs for the library design

### Miscellaneous

- Distribute as artifactr-ai, imported as artifactr ([#18](https://github.com/alexnodeland/artifactr/pull/18))
- Wrap up v0.1: evergreen status, open questions and changelog ([#17](https://github.com/alexnodeland/artifactr/pull/17))
- **deps**: Update only the lockfile, keeping supported version ranges ([#5](https://github.com/alexnodeland/artifactr/pull/5))
- Lay the foundation for the v0.1 library ([#2](https://github.com/alexnodeland/artifactr/pull/2))

[0.1.0]: https://github.com/alexnodeland/lattice/releases/tag/artifactr-v0.1.0
