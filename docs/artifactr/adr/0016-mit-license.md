# ADR-0016: MIT license

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr is a library meant to be depended on and extended by other projects, including commercial ones. Its dependencies (Pydantic, pydantic-ai, SQLAlchemy, FastAPI, the MCP SDK) are all under permissive licenses. The maintainer's other libraries use MIT.

## Decision

artifactr is licensed under the **MIT License**. The license text is in [`LICENSE`](https://github.com/alexnodeland/artifactr/blob/main/LICENSE) and declared in `pyproject.toml` with SPDX metadata (`license = "MIT"`). Contributions are accepted under the same license.

## Options considered

| Option | Adoption friction | Patent grant | Copyleft |
|---|---|---|---|
| **MIT (chosen)** | Lowest | No | No |
| Apache-2.0 | Low | Yes | No |
| MPL-2.0 | Medium | Yes | File-level |
| GPL or AGPL | High for libraries | Yes | Strong |

## Trade-off analysis

MIT matches the dependency ecosystem and the maintainer's other projects, and imposes nothing on applications built with the library. Apache-2.0's explicit patent grant is its main advantage; for a small library with no patent exposure that advantage is modest, and it can be revisited if contributors or users need it.

## Consequences

- Easier: adoption by any project, including commercial ones.
- Harder: nothing prevents proprietary forks. That is acceptable for a library whose value grows with adoption.
- Revisit if an explicit patent grant becomes important to contributors.

## Action items

1. [x] Add `LICENSE` and SPDX metadata.
2. [x] State the contribution licensing in CONTRIBUTING.md.
