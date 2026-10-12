# ADR-0007: TypeScript 7, and TypeScript 6 only where a tool needs its API

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0002][rfc-0002-tooling] chose TypeScript 7 for type checking, and asked phase 1 to confirm each tool. TypeScript 7 is the native compiler, and its package has no programmatic API at its main entry until 7.1; tools that load `typescript` as a library would need TypeScript 6 under an alias. RFC-0002 expected two: `openapi-typescript` and knip.

Phase 1 checked every tool the RFC names, on 2026-10-12:

| Tool | Version | Loads `typescript`? | Under TypeScript 7 |
|---|---|---|---|
| `typescript` | 7.0.2 | | `tsc` type-checks the web packages. Its main entry exports only `version` and `versionMajorMinor`; the API is under `typescript/unstable/*` |
| knip | 6.41.0 | No: it parses with oxc, and depends on no `typescript` | Works |
| `openapi-typescript` | 7.13.0 | Yes: a peer dependency on `typescript@^5.x`, and `ts.factory` at import | Fails at import: `Cannot read properties of undefined (reading 'createKeywordTypeNode')` |
| Vite, `@vitejs/plugin-react` | 8.3.4, 6.1.2 | No: Vite transforms with oxc | Works |
| Vitest | 5.0.3 | No | Works |
| Biome | 2.5.15 | No: it is native | Works |
| `json-schema-to-typescript`, `openapi-fetch` | 16.0.0, 0.17.0 | No | Not run; neither depends on `typescript` |
| TanStack Router's plugin, `size-limit`, `playwright-bdd` | 1.168.43, 14.2.0, 9.2.1 | No (the router's plugin uses Babel) | Not run; none depends on `typescript` |

How a tool gets TypeScript 6 matters, because it imports `typescript` by name:

- **An alias under another name** at the root, such as `typescript6`, reaches no tool.
- **Bun's nested `overrides`** (`"openapi-typescript": {"typescript": ...}`) don't apply: under Bun 1.4.3, `openapi-typescript` still loads 7.
- **TypeScript 6 as the root's `typescript`,** and 7 under another name, works for the tools, but every `tsc` on the path is then 6.
- **An alias in the one package that runs the tool** works under Bun's isolated installs: a package with `openapi-typescript` and `"typescript": "npm:typescript@6.0.3"` in its devDependencies generates types with 6, while the root's `tsc` stays 7. In that package, though, a bare `tsc` is 6.

## Decision

- **The root's `typescript` is 7.0.2,** and every web package's `typecheck` runs it.
- **Phase 1 installs no TypeScript 6.** No tool it uses loads `typescript`.
- **`openapi-typescript` alone needs TypeScript 6,** under an alias in the package that runs it. Phase 3 adds both, and settles where generation runs so that the package's own `typecheck` still runs 7.
- **A tool is checked when it is added,** against this table, and the alias goes when the tool supports 7.

## Options considered

| Option | For | Against |
|---|---|---|
| **7 at the root; 6 aliased only beside the one tool that needs it, when it is added (chosen)** | Nothing to carry until a tool needs it. Every `tsc` but one package's is 7 | Phase 3 has to keep that package's `typecheck` on 7 |
| 6 at the root as `typescript`, 7 under another name | Any tool that loads `typescript` works | Every bare `tsc` is 6, and editors pick up 6 |
| 6 under an alias at the root now, as RFC-0002 sketched | Ready for phase 3 | Reaches no tool, since none imports the alias, and knip would report it unused |

## Consequences

- Easier: type checking is the native compiler's speed, and phase 1 carries one TypeScript.
- Harder: phase 3's generation needs its own package or an explicit path to the root's `tsc`.
- To revisit: the alias goes when `openapi-typescript` supports TypeScript 7's API, from 7.1.

[rfc-0002-tooling]: ../../rfcs/0002-portalr-the-portal.md#tooling
