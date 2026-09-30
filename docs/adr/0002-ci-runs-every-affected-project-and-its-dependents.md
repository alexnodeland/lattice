# ADR-0002: CI runs every affected project and its dependents

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#moon) planned CI around `moon ci --downstream deep`: moon would find the projects a pull request touches, and `--downstream deep` would add every project that depends on one, so a change to evalr would also run the checks of artifactr, reflexr, relayr, docplan, oncall and stackr. The rehearsal found two gaps, with moon 2.5.6:

- **`--downstream deep` follows the task graph, not the project graph.** It reaches a dependent's task only through that task's own dependencies. artifactr's `check` depends on artifactr's `lint`, `typecheck` and `test`, not on anything of evalr's, so an evalr-only change ran evalr's checks alone.
- **`moon query projects --affected` sees only a project's own files.** A change to `uv.lock`, the root `pyproject.toml` or `.moon/` is in no project's directory, so it affected no package, although every Python task lists the lock and the root's configuration as inputs.

Making every `check` depend on its dependencies' (`^:check`) would make the task graph follow the project graph. It would also make `moon run artifactr:check` run evalr's checks first, every time, on a contributor's machine as in CI.

## Decision

- **`scripts/affected.py TASK` chooses what CI runs.** It asks moon which projects the change touches, by their files (`moon query projects --affected`) and by their tasks' inputs, which include the lock and the root's configuration (`moon query tasks --affected`). It adds every project that depends on one of them, all the way down, from moon's project graph, and `moon run`s the task in each project that has it. When nothing is affected, it runs nothing and succeeds.
- **CI's Check, Tests and Images jobs run through it**, with the tasks `check`, `test` and `image`, and `MOON_BASE` and `MOON_HEAD` naming the pull request's change.
- **Template and Smoke stay on `moon ci`** (`stackr:template`, `stackr:smoke`), and run only when stackr's own inputs change. Until [phase 4](../stackr/rfcs/0003-one-repository-lattice.md#phases), the template pins the libraries by revision, so a library's change can't reach what it generates ([#3](https://github.com/alexnodeland/lattice/pull/3)).
- **The edges are the `dependsOn` each `moon.yml` states,** which a root test holds to the project's `pyproject.toml`, as RFC-0003 planned.

## Options considered

| Option | An evalr-only change | `moon run artifactr:check` |
|---|---|---|
| **`scripts/affected.py` over moon's queries (chosen)** | Runs evalr's checks and every dependent's | artifactr's checks |
| `moon ci --downstream deep` (RFC-0003) | Runs evalr's checks alone | artifactr's checks |
| `^:check` in every project's `check` | Runs evalr's checks and every dependent's | evalr's checks, then artifactr's |
| Every project's checks on every pull request | Runs everything | artifactr's checks |

## Trade-off analysis

Running everything on every pull request would be correct and simple, but a change to one package would wait for all of them, and the family is growing. moon already knows which projects a change touches and what depends on what; the script joins the two answers, and leaves the task graph as narrow as a contributor's own runs need.

## Consequences

- Easier: a change to a package, or to the lock or configuration that every package reads, runs the checks of every project it can break, and no others.
- Harder: CI's selection is a script of lattice's own, which a moon upgrade could break. `nightly.yml` runs every project's `check` on `main`, whatever changed, so a gap in the selection shows there.
- Harder: moon counts a variable listed as a task's input as changed whenever it is set, so a variable CI always sets can't be an input without running its task on every pull request. The PostgreSQL URLs aren't inputs of the libraries' `test` tasks for that reason ([#23](https://github.com/alexnodeland/lattice/pull/23)); moon's cache then can't tell a run with PostgreSQL from one without it, so locally `moon run <library>:test --force` reruns the tests past a cached run.
- Revisit: if moon's `--downstream` comes to follow the project graph, and its affected projects to include their tasks' root inputs, the script can go.
