# ADR-0010: Every project's tests run in a random order

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) lists pytest-randomly under test signal, for phase 6. A test that passes only after another has run, or fails only after one, hides behind a fixed order: in file order, the same tests always run before it. pytest-randomly shuffles the modules, the classes in each, and the tests in each, and reseeds `random` (and Faker, NumPy and factory_boy when present) before each test with the run's seed.

The timeouts went into each project's `test` dependency group, beside its pytest configuration ([ADR-0007](0007-a-timeout-on-every-test-and-every-job.md)), because they need settings. pytest-randomly needs none: it is on wherever it is installed.

## Decision

- **pytest-randomly is in the root's `dev` group.** Every project's tests run from the workspace's one environment, which `uv sync --all-packages --all-groups` installs, so every project's tests, and the root's, run in a random order: locally, in CI's Check and Tests, and in Nightly.
- **No project configures it.** Each run picks a seed, and pytest prints it in its header (`Using --randomly-seed=…`).
- **An order-dependent test is fixed, not pinned.** `-p no:randomly` runs the tests in file order, to compare; a failure that only some orders show is an issue, with its seed.

On adoption, every project's tests passed under three seeds, and artifactr's and reflexr's on PostgreSQL under two more. None depended on its order.

## Options considered

| Option | Where it runs | What it costs |
|---|---|---|
| **The root's `dev` group (chosen)** | Every project, in lattice | One line |
| Each project's `test` group, as pytest-timeout is | Every project, and its tests outside lattice | Seven lines that say the same thing |
| Not at all | | Order dependence goes unseen |

## Trade-off analysis

A package's tests run only from a lattice checkout, in the workspace's environment, so its own `test` group would add nothing the root's doesn't. The root's group reaches every test run lattice makes, with nothing to keep in step.

## Consequences

- Easier: a test that leans on another's leftovers fails in some run, which prints the seed that reproduces it: `uv run pytest --randomly-seed=N`.
- Harder: two runs of the same commit can differ. A failure that only one run shows is reproduced with its seed, not dismissed as a flake.
- A new project's tests are shuffled as soon as it joins the workspace.

## Notes

- 2026-10-21: artifactr's, relayr's and grantr's moon `test` tasks run on every core through pytest-xdist, in the root's `dev` group beside pytest-randomly. Each test opens a SQLite file in a directory of its own and a PostgreSQL schema of its own, so the workers share nothing, and pytest-cov combines their coverage under the same 100% gate. Each worker collects the tests itself, so a test's id is the same in every process; and each shuffles its share, so a seed reproduces an order with the same number of workers, `-n N --randomly-seed=S`.
- 2026-10-21: a test past its minute fails by `SIGALRM` rather than ending its xdist worker, and every run lists its ten slowest tests ([ADR-0028](0028-a-stuck-test-fails-by-a-signal-and-its-worker-carries-on.md)).
