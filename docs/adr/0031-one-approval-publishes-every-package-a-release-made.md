# ADR-0031: One approval publishes every package a release made

**Status:** Accepted
**Date:** 2026-10-30
**Deciders:** Alex Nodeland

Supersedes [ADR-0023](0023-publishing-to-pypi-from-the-release-workflow.md)'s approval rule ("one approval a package, one at a time") and its "one package a dispatch". The rest of ADR-0023 stands.

## Context

Under ADR-0023 a release run never publishes. Its summary lists one `gh workflow run release.yml --ref <tag> -f tag=<tag> -f mode=publish` per package, in dependency order, and each dispatch's publishing job runs in the package's `pypi-<distribution>` environment, whose required reviewers approve it. A release of five packages is five dispatches and five approvals, each waiting for the one before. The owner approved streamlining this; [#1133](https://github.com/alexnodeland/lattice/issues/1133) had named the pain.

Two constraints shape the change. PyPI's trusted publisher names one environment per project, so each package must still publish in its own `pypi-<distribution>` environment. And those environments allow deployments from `*-v*` tags only, so a job on the release run (whose ref is `main`) cannot use them; a release run waiting for approval would also hold the `main` push concurrency group and stall release-please for every other merge.

## Decision

- **One dispatch, on a tag, names every tag the release made.** The `tag` input takes several tags separated by spaces; the run is on the first. The plan (`scripts/release_plan.py`) maps each to its package, refuses two tags of one package, and refuses any tag not at the first tag's commit (read with `git ls-remote` in the plan step), so the run still builds and attests one commit (#206). One tag alone works as before.
- **The release run's summary lists that one dispatch:** `gh workflow run release.yml --ref <first tag> -f tag="<tags in dependency order>" -f mode=publish`.
- **One approval gates it.** A job `pypi-approve` runs in a single environment, `pypi-approval`, whose required reviewers are the approval. It holds no permissions and runs after `pypi-check`, so the approver sees what PyPI would be given. `pypi-publish` needs it to succeed.
- **The publish legs are unchanged otherwise:** one leg a package in its `pypi-<distribution>` environment (trusted publishing), `max-parallel: 1`, `fail-fast`, in `STAGES` order; each verifies the attestation, checks PyPI serves what it requires, publishes and waits until PyPI serves its files. `PYPI_PUBLISH` must still be `true`.
- **The `pypi-<distribution>` environments lose their required reviewers** and keep their `*-v*` tag-only deployment policy. Otherwise each leg would ask again. `pypi-approval` gets the same tag-only policy.

## Options considered

| Option | For | Against |
|---|---|---|
| **A gate job on one environment, in a dispatch on a tag (chosen)** | One approval; the tag policy and trusted publishing stay as they are | The per-package environments no longer gate on their own |
| Publish from the release run, gated | No dispatch at all | The `*-v*` tag policy refuses `main`; a pending approval holds the push concurrency group and stalls release-please |
| Keep reviewers on every environment | No settings change | GitHub asks once a leg, and legs run one at a time: five approvals again |
| A reusable workflow per package | Separate gating | Trusted publishing checks the calling workflow's name; not tried (ADR-0023) |

## Consequences

- Easier: a release is one command and one approval; the order and the PyPI checks are the workflow's, not a person's.
- Harder: with reviewers removed from `pypi-<distribution>`, what stands between a tag and PyPI is `PYPI_PUBLISH`, the tag ruleset (only maintainers and the release App create `*-v*` tags), the environments' tag policy, and, in this workflow, `pypi-approval`. A dispatch on a tag older than this change runs that tag's `release.yml`, which has no `pypi-approve` job, and would publish its one package without approval; every such tag's version is on PyPI already, so `skip-existing` makes that a no-op, which is why reviewers are removed only once every older release is published.
- Not tested: the gate has not run. The plan is tested offline, the jobs' gating and permissions against the file, and it passes actionlint and zizmor.

## Action items

1. [x] `release.yml`: `pypi-approve`, multi-tag dispatch, one summary command; `release_plan.py` and its tests.
2. [ ] Owner, before this merges: create `pypi-approval` with the maintainer as required reviewer and deployment tags `*-v*` only (a job naming a missing environment creates it unprotected).
3. [ ] Owner, after this merges and after every release tagged before it is published: remove the required reviewers from each `pypi-<distribution>` environment, keeping its `*-v*` tag policy.
