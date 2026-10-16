# ADR-0023: Publishing to PyPI from the release workflow

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Adds the job [ADR-0006](0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md) left for later, and decides [#206](https://github.com/alexnodeland/lattice/issues/206). It answers [#7](https://github.com/alexnodeland/lattice/issues/7)'s "when": at the first release, behind a switch the maintainer turns.

## Context

`release.yml` builds each released package's wheel and sdist, attests them and attaches them to the GitHub release. None is on PyPI. The wheels require `lattice-core-ai`, which isn't there either, so a wheel from a release cannot be installed, and the libraries require one another in an order.

Two things were open. **Provenance:** `actions/attest` records the workflow's own commit as the build's source, so a release created on a later push than the one that merged its pull request has wheels built from the tag's commit and attested as built at the push (#206). **Rollout:** the first release has to be rehearsed, and published once, in an order, with the maintainer's approval.

The user decided: one release, with `0.1.0.dev0` floors in the first published wheels (raised in the next, [#213](https://github.com/alexnodeland/lattice/issues/213)); and, for #206, that the build refuses a release whose tagged commit is not the run's.

## Decision

- **A plan job decides everything first,** by `scripts/release_plan.py`, which is tested (`tests/test_release_plan.py`): the packages to build, from which commits, whether to attach, attest and publish, and in what stages. Every later job reads its outputs.
- **A release is built from the commit it was tagged at, or not at all (#206).** If release-please's `--sha` for any released package, stackr included (its images are attested the same way), is not the run's commit, the plan fails before anything is built, and its message gives the commands to run the workflow again on the tag, where the two are the same. The cost is accepted: a release created on a later push exists with no wheels until someone runs it. A released package without a full commit, or a tag whose version is not its pyproject's, is refused too.
- **The workflow can be run by hand.** On a branch, with no tag, it *rehearses*: every wheel is built (portalr's UIs and `check_wheel.py` included) and checked, at that branch's head, and nothing is attached, attested or published. On a tag, with `tag` the same, it builds that release again, from the tag, and replaces its wheels; with `mode` publish, and the repository switch on, it publishes them. Publishing by hand is refused anywhere but on a tag.
- **PyPI by trusted publishing, in stages.** The wheels attested at build are uploaded as artifacts, checked (twine, their attestations, what PyPI already has) in a job that needs no approval, and published by `pypa/gh-action-pypi-publish`, which makes PyPI's own attestations (PEP 740). Four stages, each after the one before it has been served by PyPI: `lattice-core-ai` and `evalr`; then `artifactr-ai`, `reflexr` and `grantr`; then `relayr-ai`; then `portalr`. A test holds the stages to the packages' own requirements, so a new dependency out of order fails a build. Each stage's job is in the `pypi` environment.
- **Nothing is published until the maintainer says so, twice.** The repository variable `PYPI_PUBLISH` must be `true`, and the `pypi` environment's required reviewers must approve each stage. Without the variable a release run still builds, attests and attaches, and its PyPI check says what it would do.
- **`dev0` floors in the first wheels.** Every library requires `lattice-core-ai>=0.1.0.dev0`, which a published `0.1.0` satisfies. Raising the floors to the published version is the next release's (#213).

## What the maintainer does, once

On PyPI, for each of `lattice-core-ai`, `evalr`, `artifactr-ai`, `reflexr`, `grantr`, `relayr-ai` and `portalr`, add a *pending* trusted publisher (the names are free today): owner `alexnodeland`, repository `lattice`, workflow `release.yml`, environment `pypi`. On GitHub, create the `pypi` environment with required reviewers (the maintainer), and set the repository variable `PYPI_PUBLISH` to `true` when ready. None of this is in the repository, and none was done when this was written.

To rehearse: run `gh workflow run release.yml --ref main` (rehearse is the default) and read the run: it builds every wheel at `main`'s head and prints the stages and what PyPI has. Nothing is attached, attested or published.

## Options considered

| Option | For | Against |
|---|---|---|
| **Refuse a release whose commit isn't the run's (chosen)** | Provenance always names the right commit | The release exists with no wheels until the workflow is run on the tag |
| Verify against the tag's commit afterwards | No refusal | Every consumer must; the failure comes after the release |
| Build in a workflow dispatched on the tag, always | Always right | A new trigger, and it must not publish from an arbitrary dispatch |
| Publish with an API token | No environment on PyPI | A long-lived secret; against the repository's no-external-secrets stance |
| Publish all wheels at once | Simpler | A wheel can be on PyPI before what it requires |

## Consequences

- Easier: the first release can be rehearsed in full without publishing, and a wrong-commit release can't ship a wheel with the wrong provenance.
- Harder: a release created on a later push needs a manual run on its tag, with the commands given; and the maintainer's one-time setup is required before the first publish.
- Not tested: the job has not run. The plan is tested offline, the workflow passes actionlint and zizmor, and the rehearsal is how the rest is found out before the first release.
- Revisit: when the first release is out, #213; PEP 740 attestations are PyPI's; a `testpypi` rehearsal would need a second set of pending publishers, and isn't done.
