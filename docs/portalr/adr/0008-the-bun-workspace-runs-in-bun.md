# ADR-0008: The Bun workspace runs in Bun

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[stackr RFC-0003][s-rfc-0003-bun] fixes the Bun workspace at lattice's root and moon's TypeScript tasks, and [lattice RFC-0002][rfc-0002-tooling] the tools. Phase 1 had four things left to decide: what runs the tools, how a package is consumed by another, which tasks a package without code to build or test has, and what version the web packages carry.

The tools' executables start with `#!/usr/bin/env node`, and moon runs them that way: with no Node.js on the path, `vitest` failed with exit code 127. `.prototools` installs moon, uv and Bun, and no Node.js.

## Decision

- **Bun runs every tool, in its own runtime.** Each task is `bun x --bun --no-install <tool>`: `--bun` runs a tool's Node.js script in Bun, and `--no-install` fails rather than fetching a tool that `bun.lock` doesn't hold. Biome, `tsc`, Vitest, Vite and knip all pass this way with no Node.js installed.
- **`client` and `ui` are consumed as source.** Their `exports` point at `src/index.ts`, and Vite builds them into `app` and `admin`. So they have no `build` task, and `app` and `admin` have no `test` task until they have code of their own; `check` runs whichever of `test` and `build` a package has.
- **A web package's edges are its workspace dependencies.** `app` and `admin` depend on `ui` alone until they use `client`, and the root's edges test holds each web package's `dependsOn` to its `package.json`, as it holds the Python packages' to their `pyproject.toml`.
- **The web packages are private and carry no version.** portalr's one version is its `pyproject.toml`'s, which release-please moves.
- **moon edits and installs nothing.** `.moon/toolchains.yml` turns off every setting that would install, dedupe, or rewrite a `package.json` or `tsconfig.json`. proto installs Bun from `.prototools`, as it installs moon and uv, and moon doesn't take Bun's version from there: when it did, it installed a proto of its own in CI, mid-run, and a concurrent `uv` shim failed.

## Options considered

| Option | For | Against |
|---|---|---|
| **Bun's runtime for every tool, through `bun x --bun --no-install` (chosen)** | One runtime, at the version `.prototools` pins, in CI, the dev container and locally | Vitest and Vite support Bun's runtime less widely than Node.js's |
| Node.js in `.prototools` | Every tool's documented runtime | A fourth tool to pin and update, for what Bun already runs |
| `bunfig.toml`'s `[run] bun = true` with `bun run <tool>` | Shorter commands | knip reads `bun run biome` as the file `biome.json`, and reports Biome unused |
| The runner's preinstalled Node.js | Nothing to add | Unpinned, and absent elsewhere |

## Consequences

- Easier: a contributor needs only what `proto use` installs.
- Harder: a tool that breaks under Bun's runtime needs Node.js after all; that would be a new ADR.

[rfc-0002-tooling]: ../../rfcs/0002-portalr-the-portal.md#tooling
[s-rfc-0003-bun]: ../../stackr/rfcs/0003-one-repository-lattice.md#the-bun-workspace
