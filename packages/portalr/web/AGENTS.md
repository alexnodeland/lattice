# AGENTS.md: portalr/web

The root [AGENTS.md](../../../AGENTS.md) and [portalr's](../AGENTS.md) apply; this adds what is specific to the Bun workspace. Each package below has its own.

## Layout

| Package | moon project | What it is |
|---|---|---|
| `client/` | `client` | `@portalr/client`: generated types, fetch client, WebSocket stores |
| `ui/` | `ui` | `@portalr/ui`: brand tokens, primitives, chat and artifact components |
| `app/` | `app` | The people's UI |
| `admin/` | `admin` | The UI for tenant owners, admins and operators |
| `notices/` | `notices` | `@portalr/notices`: third-party notices and the licence policy ([ADR-0033](../../../docs/portalr/adr/0033-third-party-notices-for-the-bundled-javascript.md)) |

`app` and `admin` are built by Vite into `../src/portalr/static/`, which the wheel ships; `client`, `ui` and `notices` have no `build` of their own.

## Commands

Run from anywhere; Bun runs every tool. Never use npm, pnpm, npx or Node.js.

```bash
bun install                       # from the repository root
moon run <pkg>:format             # Biome, with safe fixes
moon run <pkg>:check              # lint (Biome), typecheck (tsc 7), test (Vitest), build
moon run lattice:knip             # unused files, exports and dependencies
```

## Rules

- **TypeScript 7, strict,** from the root's `tsconfig.base.json`. **Biome** formats and lints everything here (root `biome.json`); generated files (`client/src/generated`, `*/src/routeTree.gen.ts`) are excluded from it and never edited by hand.
- **No suppressions:** no `@ts-expect-error`, `@ts-ignore`, `@ts-nocheck`, `biome-ignore`. A rule that must be off for a file goes in `biome.json`'s `overrides`, with a reason in review.
- **knip must pass.** Delete an unused export or dependency rather than keep it; a new entry point (a script, a step file) goes in the root `knip.json`.
- **Dependencies:** exact versions, no ranges; `bun.lock` records them and Renovate moves them. A sibling is named `"@portalr/<pkg>": "workspace:*"` in `package.json` *and* in `dependsOn` in that package's `moon.yml`; `tests/test_moon.py` checks the two agree.
- **No colour literals:** a colour is a token in `ui/src/tokens.css` (written by `portalr:brand`) or `base.css`.
- **Budgets:** a change that grows a bundle must stay under `../size-budget.json` (`portalr:size`); a new WebAssembly module must be in `wasm-allowlist.json` (`portalr:wasm`). A new bundled dependency must have a licence `notices/policy.json` allows.
