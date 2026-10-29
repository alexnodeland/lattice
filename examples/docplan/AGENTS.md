# AGENTS.md

The root [AGENTS.md](../../AGENTS.md) and [examples/AGENTS.md](../AGENTS.md) apply; this adds what is specific to docplan.

- docplan is artifactr's reference implementation; its image installs artifactr, evalr and lattice-core.
- A change to artifactr's public API that docplan uses lands in the same PR, with docplan updated.
- artifactr's acceptance tests run against this application (`moon run /Users/alexandernodeland/anodeland/projects/code/lattice/artifactrpi`); keep its HTTP behaviour and its committed OpenAPI document in step.
- `Dockerfile.dockerignore` and the `image` task's `inputs` in [moon.yml](moon.yml) name the same files; change both.
- Run `moon run docplanheck` and `moon run docplan:image` after a change.
