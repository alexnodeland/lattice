# ADR-0018: lattice-core, what the libraries share

**Status:** Accepted, amended by [ADR-0020](0020-the-telemetry-contract-needs-no-extra.md) and [ADR-0021](0021-the-refusal-schema-needs-no-extra.md)
**Date:** 2026-10-13
**Deciders:** Alex Nodeland
**Amends:** [reflexr ADR-0003](../reflexr/adr/0003-independent-sibling-of-artifactr.md): artifactr and reflexr still import neither each other nor grantr, but they share one package

## Context

reflexr ADR-0003 kept artifactr and reflexr independent, with aligned conventions, and deferred a shared kernel "from two proven implementations, if the third system shows it pays". relayr is that third system, and grantr and portalr came after it. Since then, code that must stay identical has been copied between the packages, each copy marked "shared verbatim … change both" or "change all four" ([lattice #73](https://github.com/alexnodeland/lattice/issues/73)). The markers keep the copies in step by review alone, and their docstrings had started to drift.

What is copied, word for word but for the package's name:

- in artifactr, reflexr, grantr and relayr: the SQLite engine, the tenant session for row-level security, and the session helpers SQL storage locks and awaits with;
- in artifactr and reflexr: the OpenTelemetry setup, with the access-token redaction; the Langfuse client (which only looked alike, and stayed per library: [ADR-0020](0020-the-telemetry-contract-needs-no-extra.md)); the MCP server's logging guard; the LiteLLM model; `tag_required`; and the search for a NUL character;
- in artifactr, reflexr and portalr: the REST routers' refusal schema, `RejectionDetail`, `FieldError`, `Refused` and `REFUSALS`.

## Decision

- **A small package, `lattice-core`,** holds what the packages share and must keep identical. Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`. It is a package of lattice like the others: in the uv workspace and moon, tested at 100% coverage, released by release-please, and built for PyPI. Nothing is published yet. *lattice-core-ai 0.1.0 has been on PyPI since 2026-10-17 ([ADR-0023](0023-publishing-to-pypi-from-the-release-workflow.md#amendment-2026-10-16)).*
- **Who imports whom.** artifactr, reflexr and grantr import none of one another. relayr is the bridge, and imports artifactr and reflexr. Any package may depend on lattice-core, which imports no lattice package: a test holds its shipped code to the standard library, pydantic, and what its extras declare.
- **Only infrastructure, and only what is truly the same.** Code moves in when two or more packages have it word for word, but for their names. Code that only looks alike stays where it is, such as the LiteLLM gateways' guardrail policies, the storages and the migrations. Nothing about a package's domain belongs in it: review enforces that, as the test can't.
- **Each package keeps its public API** by re-exporting what it made public, so an application never imports lattice-core. A package raises its own errors around lattice-core's helpers, which raise none of theirs, and its docstrings name no package.
- **It changes only by addition and deprecation.** A name it removes is deprecated first, for a release, so a library on an older lower bound keeps working. Each library requires a lower bound of it, raised by hand when the library needs something new.
- **It moves in over four pull requests,** each removing the markers it resolves:
  1. the package, with `tag_required` and the NUL search;
  2. the SQL helpers, behind a `sql` extra, for artifactr, reflexr, grantr and relayr;
  3. the OpenTelemetry setup and the redaction, the MCP logging guard, the LiteLLM model and Langfuse's span filters, behind extras, for artifactr and reflexr (the Langfuse client stayed per library, see [ADR-0020](0020-the-telemetry-contract-needs-no-extra.md));
  4. the routers' refusal schema, in `lattice_core.fastapi` behind a `fastapi` extra, for artifactr, reflexr and portalr.

## Options considered

| Option | For | Against |
|---|---|---|
| **A small shared package (chosen)** | One copy, tested once; no markers to keep | One more package to release, and a dependency of every library |
| One library owns the code, the others import it | No new package | artifactr and reflexr would import each other, which ADR-0003 rules out |
| One source, copied into each package and checked for drift | The libraries keep no shared dependency | Generated copies in every package, still tested in each |
| Keep the copies, with a test that the marked blocks match | Nothing moves | The duplication stays, and grows with each package |

## Consequences

- Easier: a fix to shared infrastructure is made once, and reaches every package.
- Harder: a library's release can need lattice-core's first; its lower bound says which.
- Harder: a pip user, until the packages are on PyPI, installs lattice-core-ai from lattice as well; uv takes it from the same commit as the library. *lattice-core-ai is on PyPI since 2026-10-17, so pip takes it from there.*
