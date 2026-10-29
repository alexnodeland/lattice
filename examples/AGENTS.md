# AGENTS.md

The root [AGENTS.md](../AGENTS.md) applies; this adds what is specific to the reference implementations.

## What these are

- [docplan/](docplan/) is artifactr's reference implementation; [oncall/](oncall/) is reflexr's. They show how an application uses the library, and the libraries' acceptance tests run against them (ADR-0015).
- They are applications (`layer: 'application'` in `moon.yml`): they may import the libraries; no library may import them.
- Keep them idiomatic: they are what users copy. Prefer the library's public API over internals.

## Rules

- 100% branch coverage of each example's own `src/` (`fail_under = 100`), like the packages.
- An example's `dependsOn` in `moon.yml` must match its `pyproject.toml` (`tests/test_moon.py`).
- Images are built from lattice's root: `moon run docplan:image`, `moon run oncall:image` (via `scripts/image`).
- `Dockerfile.dockerignore` is an allow-list. A new file or library the image needs must be added there **and** to the `image` task's `inputs` in `moon.yml`, together.
- `README.md` is in the image (package metadata names it); keep it accurate.

## Commands

```bash
moon run docplan:check
moon run docplan:image
```
