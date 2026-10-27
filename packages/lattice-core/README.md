<p align="center">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/lattice-core/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-9E0A5E"></a>
</p>

**lattice-core** is what lattice's packages share and must keep identical. artifactr, reflexr and grantr import none of one another, and relayr bridges artifactr and reflexr; where two of them would otherwise copy the same code, they depend on lattice-core, which imports no lattice package. Each re-exports what it makes public, so an application imports from the package it uses, never from here.

> **Status:** it holds `tag_required`, the JSON Schema helper for tagged unions; `holds_nul`, which finds text PostgreSQL can't store; `web_origin` and `origins`, which check the origins a portal, its sandbox and its editors are told; and, behind extras (the telemetry contract, `lattice_core.otel.contribution`, needs none), the SQL helpers the libraries' storages share, their OpenTelemetry setup, Langfuse's span filters and the LiteLLM model; `logging_left_alone`, which puts the root logger back as the application configured it; and the REST routers' refusal schema ([lattice ADR-0018](https://lattice.alexnodeland.com/adr/0018-lattice-core-what-the-libraries-share/) and [ADR-0021](https://lattice.alexnodeland.com/adr/0021-the-refusal-schema-needs-no-extra/)). Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`.

Only infrastructure that is the same in two or more packages belongs here, never a package's domain. See [lattice-core's documentation](https://lattice.alexnodeland.com/lattice-core/).
