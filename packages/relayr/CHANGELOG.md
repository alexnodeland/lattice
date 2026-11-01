# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0](https://github.com/alexnodeland/lattice/compare/relayr-v0.3.0...relayr-v0.4.0) (2026-11-01)


### Features

* **core:** parity: every operation names its command, and one test holds the catalogs to grantr (RFC-0014 P13) ([#1366](https://github.com/alexnodeland/lattice/issues/1366)) ([0138269](https://github.com/alexnodeland/lattice/commit/013826911c9cb515ef3c45ad49c0afb396f876de))

## [0.3.0](https://github.com/alexnodeland/lattice/compare/relayr-v0.2.1...relayr-v0.3.0) (2026-11-01)


### Features

* **relayr:** relayr's commands, the tracker connector's reads gated by reflexr's actions (RFC-0014 phase 1) ([#1341](https://github.com/alexnodeland/lattice/issues/1341)) ([7bfe389](https://github.com/alexnodeland/lattice/commit/7bfe38922e59515afe7c5c50affd0eabfd8211da))

## [0.2.1](https://github.com/alexnodeland/lattice/compare/relayr-v0.2.0...relayr-v0.2.1) (2026-10-30)


### Bug Fixes

* **stack:** name each pg-up's compose project with a random token ([#1163](https://github.com/alexnodeland/lattice/issues/1163)) ([585b868](https://github.com/alexnodeland/lattice/commit/585b8689a4cdc68475c994b32b9e3bc57a91c64e))

## [0.2.0](https://github.com/alexnodeland/lattice/compare/relayr-v0.1.1...relayr-v0.2.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730))
* **artifactr,portalr:** `ask_user` takes `questions` (one to four, each with `question`, `header`, two to four `options` of `label`, `description` and `recommended`, and `multiple` and `other`) in place of `question` and `choices`. An `answer_deferred` to it carries `{"answers": [{"selected": [...], "other": ...}, ...]}`, one per question, or `{"reply": ...}`; a plain string is refused as `validation_failed`. The agent's call returns each question beside its answer. The protocol schema names the shapes `ask_user` and `ask_user_answer`. This is a break in the wire contract, which the griffe-based breaks check (lattice ADR-0012) doesn't cover; it is marked here and in the title.

### Features

* **artifactr,grantr:** a message chooses the model of the turn it starts ([#823](https://github.com/alexnodeland/lattice/issues/823)) ([97ab516](https://github.com/alexnodeland/lattice/commit/97ab516bf785c48606073a41790a01870da0f496))
* **artifactr,portalr:** ask_user asks questions with options, and the chat shows tool calls, sides, failures and its stream ([#423](https://github.com/alexnodeland/lattice/issues/423)) ([7463e94](https://github.com/alexnodeland/lattice/commit/7463e945526c4ce7156d2b279e2da54b82158824))
* **artifactr:** diagrams' revisions thinned, and workspaces tended every hour ([#730](https://github.com/alexnodeland/lattice/issues/730)) ([fcdefda](https://github.com/alexnodeland/lattice/commit/fcdefdaf158922e780c482f24ee2b4250f7dd657))
* **diagrams:** a diagram's commits bridged as its elements changed, and comments on them ([#733](https://github.com/alexnodeland/lattice/issues/733)) ([d69702d](https://github.com/alexnodeland/lattice/commit/d69702dd651f43e581439d4329b418d21f43c7ae))
* **portalr:** tracker links on runs, and relayr's reads for the portal (lattice RFC-0004, phase 3) ([#391](https://github.com/alexnodeland/lattice/issues/391)) ([d4f3500](https://github.com/alexnodeland/lattice/commit/d4f35002fffc723c4259ddcafd1704df9a886b70))
* **relayr:** file and change items in Plane and Vikunja, once (lattice RFC-0004, phase 1) ([#348](https://github.com/alexnodeland/lattice/issues/348)) ([7a054d3](https://github.com/alexnodeland/lattice/commit/7a054d3eb3dcec6b66536d0586004e0f8561f867))
* **relayr:** read back what people change in Plane and Vikunja (lattice RFC-0004, phase 2) ([#380](https://github.com/alexnodeland/lattice/issues/380)) ([857ccdb](https://github.com/alexnodeland/lattice/commit/857ccdb00d7e8be8226193e6396c41ce7fdfd0e6))
* **ui:** forms and dashboards in the chat, phase 1 of RFC-0005, in artifactr and relayr ([#355](https://github.com/alexnodeland/lattice/issues/355)) ([423f37a](https://github.com/alexnodeland/lattice/commit/423f37a24d2f15a33c23c1586569becb60defd08))
* **ui:** forms and dashboards in the chat, portalr's renderers, phase 1 of RFC-0005 ([#392](https://github.com/alexnodeland/lattice/issues/392)) ([c78e43e](https://github.com/alexnodeland/lattice/commit/c78e43e03be8dc296700e2e30b7569f3a35ba851))
* which kinds an agent's edits apply to directly in Auto, per workspace ([#1109](https://github.com/alexnodeland/lattice/issues/1109)) ([640b338](https://github.com/alexnodeland/lattice/commit/640b3385022e1edd0ed487cf787e40fe7591e08f)), closes [#874](https://github.com/alexnodeland/lattice/issues/874)

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
