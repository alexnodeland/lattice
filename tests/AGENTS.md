# AGENTS.md

The root [AGENTS.md](../AGENTS.md) applies; this adds what is specific to lattice's own tests.

## What lives here

These are the root project's tests: repository-wide invariants, not any package's unit tests (those live in `packages/<pkg>/tests/`).

- `test_quality.py`: the quality gates over every package's, the examples' and the root's Python, and portalr's TypeScript; it fails on any inline suppression.
- `test_moon.py`: each project's `dependsOn` in `moon.yml` matches what its `pyproject.toml` or `package.json` requires.
- `test_affected.py`, `test_release_*.py`, `test_pypi.py`, `test_tlc.py`, `test_craft.py`, `test_check_spec.py`: tests for [scripts/](../scripts/).
- `test_stackr_*.py`, `test_portalr_*.py`, `test_grantr_*.py`, `test_font_notices.py` and others: invariants across files that no single package's tests can see.
- `test_enforcement_suite.py`: lattice RFC-0011's one suite for every capability provider. It runs tiers, grants, limits, taint, approvals and audit against a fake provider of each kind and against each library's real provider. A library's new provider joins its `SUBJECTS`.
- `fixtures/` holds their inputs.

## Running them

```bash
moon run lattice:test                     # all of them, as CI does
uv run pytest tests/test_moon.py -n0      # one file
```

## Rules

- Tests read the repository from `ROOT = Path(__file__).parent.parent`; don't depend on the working directory.
- They run in a random order with warnings as errors, under pyright strict like `scripts/`.
- A new input a test reads must be in `lattice:test`'s `inputs` in the root [moon.yml](../moon.yml), or moon's cache won't rerun it.
