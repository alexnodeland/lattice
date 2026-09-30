# ADR-0025: Distributed as artifactr-ai, imported as artifactr

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

The name `artifactr` on PyPI belongs to an unrelated project (a tool for managing AI artifacts across configurations), so the library cannot be published under its own name. The import name `artifactr` is used throughout the code, the docs and every application built on the library.

## Decision

- The distribution is named **`artifactr-ai`**: `uv add artifactr-ai`, `pip install "artifactr-ai[fastapi]"`.
- The import name stays **`artifactr`**. `[tool.uv.build-backend] module-name = "artifactr"` builds the `artifactr` package into the `artifactr-ai` wheel.
- Extras keep their names (`fastapi`, `mcp`, `sql`, `postgres`, `sqlite`), so `artifactr-ai[postgres]` replaces `artifactr[postgres]`. Earlier ADRs keep the old spelling, as the record of their time.
- The install docs say that `artifactr` on PyPI is a different project.

## Options considered

| Option | Cost | Downside |
|---|---|---|
| **`artifactr-ai` (chosen)** | Change the distribution name only | Install and import names differ |
| Rename the import package too | Every import, doc and example | Loses the project's name |
| Ask PyPI to transfer `artifactr` (PEP 541) | Only waiting | The project is active, so a transfer is unlikely, and publishing waits on it |

Other free names (`pyartifactr`, `artifactr-sdk`, `artifactr-kit`) were considered. `artifactr-ai` says what the library is for and follows the `pydantic-ai` pattern.

## Consequences

- Easier: the library can be published without waiting on anyone.
- Harder: people may type `pip install artifactr` and get the unrelated project. The README and getting-started page warn against it.
- `importlib.metadata.version("artifactr-ai")` supplies `artifactr.__version__`.

## Action items

1. [x] Rename the distribution, point the example's dependency at it, and update the install docs.
2. [ ] Publish `artifactr-ai` to PyPI when the maintainer decides to.
