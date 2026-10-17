# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1](https://github.com/alexnodeland/lattice/compare/relayr-v0.1.0...relayr-v0.1.1) (2026-10-17)


### Bug Fixes

* **deps:** raise the floors on sibling packages to their released versions ([#333](https://github.com/alexnodeland/lattice/issues/333)) ([54ff956](https://github.com/alexnodeland/lattice/commit/54ff9566b418ab8bcbdb797385c2dc0b6e0a10e5))

## 0.1.0 (2026-10-17)


### ⚠ BREAKING CHANGES

* **reflexr:** `Storage` has a new method, `rule_history`, which a storage implemented outside reflexr must add. Migration 0008 adds a column and a partial index to `reflexr_events`, holding the table while it runs. relayr's `INSTALLS_READ` is removed.
* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112))
* **relayr:** `Followers` and `bridged_turns` no longer take `read_back`. `turn_cause` now takes `(ledger, workspace, message_ids)`, the turn's workspace key and its messages, in place of `(ledger, source, turn, *, before_seq, read_back)`.

### Features

* **artifactr,reflexr:** LiteLLM requests carry the trace tags Langfuse propagates ([#203](https://github.com/alexnodeland/lattice/issues/203)) ([f8423ca](https://github.com/alexnodeland/lattice/commit/f8423ca118385eb81d7a33b0ea405970c7cb05da))
* **lattice-core:** the OpenTelemetry setup, Langfuse's span filters, the LiteLLM model and the logging guard ([#187](https://github.com/alexnodeland/lattice/issues/187)) ([508d276](https://github.com/alexnodeland/lattice/commit/508d2761b583837e2aeb99880e930a75ed4c32c3))
* **lattice-core:** the SQL helpers the libraries' storages share, behind a sql extra ([#186](https://github.com/alexnodeland/lattice/issues/186)) ([9b6a571](https://github.com/alexnodeland/lattice/commit/9b6a57144d9efdfd933d66b80a86a87ce7e10a8c))
* **reflexr:** a stored rule's history, read by its name, so relayr finds its installs however far back ([#151](https://github.com/alexnodeland/lattice/issues/151)) ([66e096a](https://github.com/alexnodeland/lattice/commit/66e096aff95e3eabe25a5c02603fb0c7cff8616c))
* **relayr:** a retried send asks again, and turns are traced by their messages ([#109](https://github.com/alexnodeland/lattice/issues/109)) ([1cb0d20](https://github.com/alexnodeland/lattice/commit/1cb0d200148dd553edefc6cf732f99e53ca7fff0))
* **relayr:** a rule changed in reflexr directly is proposed back to its artifact ([#136](https://github.com/alexnodeland/lattice/issues/136)) ([eee4893](https://github.com/alexnodeland/lattice/commit/eee4893c753f62c614f0cc72e4ea588fe296a11a))
* **relayr:** an allowlist for a whole rule namespace ([#122](https://github.com/alexnodeland/lattice/issues/122)) ([2c1f33d](https://github.com/alexnodeland/lattice/commit/2c1f33d3e5e98052577d7346d10a122f4c82aeb3))
* **relayr:** proposal outcomes as feedback, and measures of the bridge's rules ([#138](https://github.com/alexnodeland/lattice/issues/138)) ([f742084](https://github.com/alexnodeland/lattice/commit/f742084ab5286b612ec7d761d320524f67d1638d))
* **relayr:** row-level security in the SQL ledger, with the followers' start on the owner's engine ([#106](https://github.com/alexnodeland/lattice/issues/106)) ([437ae71](https://github.com/alexnodeland/lattice/commit/437ae71cd2432e0268a189d04cf466501967e3a1))
* **relayr:** rules from chat, drafted, previewed, and installed once a person accepts ([#119](https://github.com/alexnodeland/lattice/issues/119)) ([3d49ba4](https://github.com/alexnodeland/lattice/commit/3d49ba4dbdabbb04e24b019fbcab941211fc7c6d))
* **relayr:** the inbound adapter, with followers, the ledger and the bridged types ([#70](https://github.com/alexnodeland/lattice/issues/70)) ([ce51f03](https://github.com/alexnodeland/lattice/commit/ce51f03ca740b903b50c6996ae86b3ab20893c18))
* **relayr:** the outbound adapter, allowlists and chains that continue across the bridge ([#77](https://github.com/alexnodeland/lattice/issues/77)) ([3ceaa57](https://github.com/alexnodeland/lattice/commit/3ceaa57e53e7bd493f72169c2532e7da526606b0))
* **relayr:** traces linked across the bridge, sessions tagged with each other, and counters ([#87](https://github.com/alexnodeland/lattice/issues/87)) ([0a08698](https://github.com/alexnodeland/lattice/commit/0a086984fb73e50486d0f6158285e281976da237))


### Bug Fixes

* **grantr:** a service principal's id can't pass for the libraries' own actors ([#112](https://github.com/alexnodeland/lattice/issues/112)) ([77b7ab3](https://github.com/alexnodeland/lattice/commit/77b7ab3ef0e3ddbfe1da8f4fbff22aa03a6ba0b5))
* **relayr:** wait for every span the bridge's trace test reads ([#107](https://github.com/alexnodeland/lattice/issues/107)) ([3d24cbc](https://github.com/alexnodeland/lattice/commit/3d24cbc1917c358ac4c1d58ff0460671bff4dbea))

## [Before lattice]

### Miscellaneous

- The foundation, in progress: tooling, brand files, ADRs and the v0.1 plan
