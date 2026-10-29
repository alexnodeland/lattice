# AGENTS.md

The root [AGENTS.md](../AGENTS.md) applies; this adds what is specific to the repository's tools. Each script's header says what it does and how to call it; read it first, and keep it current.

## The scripts

| Script | What it does |
|---|---|
| `affected.py` | Runs a task in every project a change affects and every dependent (CI's jobs) |
| `breaks.py` | Fails on an unmarked break in a package's public API (`lattice:breaks`) |
| `release_plan.py`, `release_pr_diff.py` | Plan a release's builds; recognise a release-only pull request |
| `pypi.py`, `attach-assets`, `verify-attestation` | Release workflow: what PyPI serves, release assets, attestations |
| `standalone.py`, `lowest_direct.py` | Install a wheel outside the workspace, at built or floor versions, and import it |
| `check_site.py` | Finds lists in the built site that rendered as text (`lattice:docs`) |
| `check_spec.py` | Holds each formal spec in `docs/<package>/spec/` to its README, code and tests |
| `griffe_sphinx_roles.py` | Griffe extension: Sphinx roles in docstrings become mkdocstrings links |
| `api`, `image` | A package's acceptance tests; an example's image, each as its own compose project |
| `compose-project.sh` | Sourced by those: names a compose project with a random token |
| `dev`, `check-dev` | `make dev`'s stack and application; `check-dev` checks `dev` against fakes |
| `tlc`, `tlc.sha256` | Model-check a TLA+ spec with the pinned, checksummed `tla2tools.jar` |
| `craft`, `crafts/*.sha256` | Fetch a crafting app at its pinned release and checksum |

## Rules

- Python here is under pyright strict and ruff (`moon run lattice:typecheck`, `moon run lattice:lint`).
- Tests for scripts live in the root [tests/](../tests/), e.g. `tests/test_affected.py`, `tests/test_tlc.py`, `tests/test_craft.py`. A changed script needs its test changed.
- Shell scripts use `set -euo pipefail` and pass shellcheck (pre-commit). A change to `dev` must keep `moon run lattice:check-dev` passing.
- Changing a pin (`tlc.sha256`, `crafts/*.sha256`) means changing the version and its SHA-256 together.
