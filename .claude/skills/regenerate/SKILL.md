---
name: regenerate
description: Regenerate lattice's committed, generated files (JSON Schemas, OpenAPI documents, Grafana dashboards, portalr's brand tokens, the client's types) after changing what they come from, so the drift tests pass. Use after editing protocol models, a FastAPI router, a dashboard's source or the brand, or when a test fails because a generated file drifted.
---

# Regenerate the generated files

Generated files are committed, and a test fails when one drifts from its source. Never edit them by hand: change the source and run its task.

| Changed | Run | Writes |
|---|---|---|
| artifactr's or reflexr's protocol models, or their REST router | `moon run artifactr:schema`, `moon run reflexr:schema` | `packages/<pkg>/schemas/` |
| grantr's admin router | `moon run grantr:schema` | `packages/grantr/schemas/` |
| relayr's models or router | `moon run relayr:schema` | `packages/relayr/schemas/` |
| portalr's router | `moon run portalr:schema` | `packages/portalr/schemas/` |
| artifactr's or reflexr's metrics or dashboard source | `moon run artifactr:dashboards`, `moon run reflexr:dashboards` | `packages/<pkg>/deploy/grafana/dashboards/` |
| portalr's default brand kit (`src/portalr/brand/`) | `moon run portalr:brand` | `packages/portalr/web/ui/src/tokens.css` |
| any package's committed OpenAPI document (after the `schema` task) | `moon run client:types` | `packages/portalr/web/client`'s generated types |

The client's types come from the packages' documents, so a router change is two steps: the package's `schema`, then `client:types`.

Then:

1. `git status` to see what changed; review the diff of each generated file, which is the change's public surface.
2. Run the drift tests: `moon run <project>:test` for each project whose files changed (and `client:test` after `client:types`).
3. A changed schema or OpenAPI document may be a break in the public API: `moon run lattice:breaks`, and mark the PR title with `!` if it is one.
