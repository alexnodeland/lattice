# Changelog

## [0.2.0](https://github.com/alexnodeland/lattice/compare/lattice-core-v0.1.0...lattice-core-v0.2.0) (2026-10-24)


### Features

* **artifactr,portalr:** connected apps, an operator's own FreeCAD or Blender through a vetted MCP server, code approved on every call ([#450](https://github.com/alexnodeland/lattice/issues/450)) ([5fbb431](https://github.com/alexnodeland/lattice/commit/5fbb431eb763dffa58d946bb25917121fda54067))
* **artifactr:** diagrams' data: an element-scoped patch, its checks and what the agent reads, with diagrams off by default ([#563](https://github.com/alexnodeland/lattice/issues/563)) ([9f8f2d5](https://github.com/alexnodeland/lattice/commit/9f8f2d571a766e78c8a3e86693732608dbb9a6d8))
* **files:** Blender as native files, on the script dialect, with no file that may run Python ([#445](https://github.com/alexnodeland/lattice/issues/445)) ([6b55967](https://github.com/alexnodeland/lattice/commit/6b5596713c023bf205cefcb4d42cdeede7dec9e4))
* **files:** every crafting app declared once, on two dialects' adapters, pinned on its own ([#394](https://github.com/alexnodeland/lattice/issues/394)) ([3d1c635](https://github.com/alexnodeland/lattice/commit/3d1c635b07c7cb2eb4dad039c206a08196bc6760))
* **files:** FilmCraft, EffectCraft and SoundCraft projects as native files, kept only whole, and LightCraft export only ([#447](https://github.com/alexnodeland/lattice/issues/447)) ([0d6d4db](https://github.com/alexnodeland/lattice/commit/0d6d4db26591566314383282e6a163062dd42373))
* **files:** FreeCAD as native files, on a script dialect, with no Python a file or an agent brings ([#428](https://github.com/alexnodeland/lattice/issues/428)) ([2bced02](https://github.com/alexnodeland/lattice/commit/2bced0258e8bc8c9f819445b34ce0b8704163483))
* **integrations:** one switch per workspace for every integration: lattice-core's port, grantr's store and artifactr's gate ([#369](https://github.com/alexnodeland/lattice/issues/369)) ([bec7dfd](https://github.com/alexnodeland/lattice/commit/bec7dfd99b4d35a74bea8cd757e941b0d9df315b))
* **lattice-core,artifactr:** a connected app's tools narrowed per workspace, and the operator's offer of reads and edits ([#645](https://github.com/alexnodeland/lattice/issues/645)) ([b50d261](https://github.com/alexnodeland/lattice/commit/b50d2617f7a5259d0bedf374b2f942971447d287))
* **lattice-core,grantr,artifactr:** settings each tier may only narrow, stored and audited in grantr, and a connected app's hourly limit read from them ([#609](https://github.com/alexnodeland/lattice/issues/609)) ([8b23639](https://github.com/alexnodeland/lattice/commit/8b236399fdcf3bd7cfb87dd89f3cdaec89e1022c))
* **portalr,grantr,lattice-core:** admin's Settings page, where a level's limits are lowered at the version read, and a changed registry's clamping flagged ([#625](https://github.com/alexnodeland/lattice/issues/625)) ([759505c](https://github.com/alexnodeland/lattice/commit/759505ca8ff08ade1929a2b165c7d00d054311b9))
* **portalr,lattice-core,grantr:** a connected app's tools chosen in admin by checkbox, each with its risk, and Settings opened to a workspace's admins ([#661](https://github.com/alexnodeland/lattice/issues/661)) ([1cf8395](https://github.com/alexnodeland/lattice/commit/1cf83959913d9ba7b5681e861a98be76be157fc9))
* **ui:** forms and dashboards in the chat, portalr's renderers, phase 1 of RFC-0005 ([#392](https://github.com/alexnodeland/lattice/issues/392)) ([c78e43e](https://github.com/alexnodeland/lattice/commit/c78e43e03be8dc296700e2e30b7569f3a35ba851))


### Bug Fixes

* four CI tickets: the select's Tab test, a warning for a second configure_telemetry, and the image tasks' compose projects ([#345](https://github.com/alexnodeland/lattice/issues/345)) ([09b0389](https://github.com/alexnodeland/lattice/commit/09b0389283d63744e324f66e0454a6e8f029e653)), closes [#193](https://github.com/alexnodeland/lattice/issues/193)

## 0.1.0 (2026-10-17)


### Features

* **artifactr,reflexr:** LiteLLM requests carry the trace tags Langfuse propagates ([#203](https://github.com/alexnodeland/lattice/issues/203)) ([f8423ca](https://github.com/alexnodeland/lattice/commit/f8423ca118385eb81d7a33b0ea405970c7cb05da))
* **lattice-core:** a tenant-workspace tag on every LiteLLM request, so spend reads per tenant's workspace ([#190](https://github.com/alexnodeland/lattice/issues/190)) ([95ffe96](https://github.com/alexnodeland/lattice/commit/95ffe9641ecce3797dcfa6dd2276cdcb08d00920))
* **lattice-core:** one package for what the libraries share, starting with tag_required and the NUL check ([#175](https://github.com/alexnodeland/lattice/issues/175)) ([e3074fc](https://github.com/alexnodeland/lattice/commit/e3074fc6afd9e362f263dc8964fe386e8fa65efa))
* **lattice-core:** the OpenTelemetry setup, Langfuse's span filters, the LiteLLM model and the logging guard ([#187](https://github.com/alexnodeland/lattice/issues/187)) ([508d276](https://github.com/alexnodeland/lattice/commit/508d2761b583837e2aeb99880e930a75ed4c32c3))
* **lattice-core:** the routers' refusal schema, shared by artifactr, reflexr and portalr ([#200](https://github.com/alexnodeland/lattice/issues/200)) ([1b335b1](https://github.com/alexnodeland/lattice/commit/1b335b1320d8d6ec14a185e4911e9c0c94dac221))
* **lattice-core:** the SQL helpers the libraries' storages share, behind a sql extra ([#186](https://github.com/alexnodeland/lattice/issues/186)) ([9b6a571](https://github.com/alexnodeland/lattice/commit/9b6a57144d9efdfd933d66b80a86a87ce7e10a8c))

## Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
