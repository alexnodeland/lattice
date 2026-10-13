# ADR-0018: lattice-core, what the libraries share

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland
**Amends:** [reflexr ADR-0003](../reflexr/adr/0003-independent-sibling-of-artifactr.md): the libraries still never import one another, but they share one package

## Context

reflexr ADR-0003 kept artifactr and reflexr independent, with aligned conventions, and deferred a shared kernel "from two proven implementations, if the third system shows it pays". relayr is that third system, and grantr a fourth. Since then, code that must stay identical has been copied between them, each copy marked "shared verbatim … change both" or "change all four" ([lattice #73](https://github.com/alexnodeland/lattice/issues/73)):

- in all four: the SQLite engine, the tenant session for row-level security, and the session helpers SQL storage locks and awaits with;
- in artifactr and reflexr: the OpenTelemetry setup, the access-token redaction, the Langfuse client, the MCP server's logging guard, the LiteLLM model, `tag_required`, and the check for a NUL character.

The markers keep the copies in step by review alone, and they had started to drift in their docstrings.

## Decision

- **A small package, `lattice-core`,** holds what the libraries share and must keep identical. Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`. It is a package of lattice like the others: in the uv workspace and moon, tested at 100% coverage, released by release-please, and built for PyPI. Nothing is published yet.
- **Every library may depend on it, and on nothing else of lattice's but what it already does.** The libraries still never import one another. lattice-core imports none of them.
- **Only infrastructure, and only what is truly the same.** Code moves in when two or more libraries have it word for word, but for their names. Code that only looks alike, such as the LiteLLM gateways' guardrail policies, the storages and the migrations, stays where it is. Nothing about a library's domain belongs in it.
- **Each library keeps its public API** by re-exporting what it made public, so an application never imports lattice-core. A library raises its own errors around lattice-core's helpers, which raise none of theirs.
- **It moves in over four pull requests:** the package, with `tag_required` and the NUL check; the SQL helpers; the OpenTelemetry setup, with the redaction, the Langfuse client, the MCP logging guard and the LiteLLM model, if it stays the same; each removing the markers it resolves.

## Options considered

| Option | For | Against |
|---|---|---|
| **A small shared package (chosen)** | One copy, tested once; no markers to keep | One more package to release, and every library's dependency |
| One library owns the code, the others import it | No new package | The libraries would import one another, which ADR-0003 rules out |
| One source, copied into each package and checked for drift | The libraries stay free of a shared dependency | Generated copies in every package, still tested four times |
| Keep the copies, with a test that the marked blocks match | Nothing moves | The duplication stays, and grows with each library |

## Consequences

- Easier: a fix to shared infrastructure is made once, and reaches every library.
- Harder: a library's release can need lattice-core's first. Their ranges say which.
- Harder: a pip user, until the packages are on PyPI, installs lattice-core-ai from lattice as well; uv takes it from the same commit as the library.
