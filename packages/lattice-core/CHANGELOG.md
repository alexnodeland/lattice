# Changelog

## [0.1.1](https://github.com/alexnodeland/lattice/compare/lattice-core-v0.1.0...lattice-core-v0.1.1) (2026-10-17)


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
