# AGENTS.md

The root [AGENTS.md](../../AGENTS.md) and [examples/AGENTS.md](../AGENTS.md) apply; this adds what is specific to oncall.

- oncall is reflexr's reference implementation; its image installs reflexr, evalr and lattice-core.
- A change to reflexr's public API that oncall uses lands in the same PR, with oncall updated.
- reflexr's acceptance tests run against this application (`moon run /Users/alexandernodeland/anodeland/projects/code/lattice/reflexrpi`); keep its HTTP behaviour and its committed OpenAPI document in step.
- `Dockerfile.dockerignore` and the `image` task's `inputs` in [moon.yml](moon.yml) name the same files; change both.
- Run `moon run oncallheck` and `moon run oncall:image` after a change.
