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

- **A plan job decides everything first,** by `scripts/release_plan.py`, which is tested (`tests/test_release_plan.py`): the packages to build, from which commits, whether the run writes, whether it publishes, and in what order. Every later job reads its outputs.
- **A release is built from the commit it was tagged at, or not at all (#206).** If release-please's `--sha` for any released package, stackr included (its images are attested the same way), is not the run's commit, the plan fails before anything is built. Its message gives the command to run the workflow again on the tag, where the two are the same, and says what that command does: for a wheel, it attaches and attests the wheels and publishes to PyPI only if `PYPI_PUBLISH` is true, after the `pypi` environment's approval of each package; for stackr, it builds the images again, pushes them and adds them to the release's notes, and PyPI is not in it. The cost is accepted: a release created on a later push exists with no wheels until someone runs it. A released package without a full commit, or a tag whose version is not its pyproject's, is refused too.
- **A rehearsal writes nothing, anywhere.** The workflow can be run by hand, and `mode` is `rehearse` unless it says `publish`. A rehearsal, on a branch (every wheel at its head) or on a tag (that release, again), builds and checks, and attaches nothing to a release, attests nothing, pushes no image, rewrites no release notes and publishes nothing. It keeps the files it built as artifacts of the run, and nothing else. This is structural, not a matter of care: the build job's permissions are `contents: read`, and the jobs that can write (`attach`, `publish-images`, `release-notes`, `pypi-publish`) run only where the plan writes; a test holds both. Attaching, attesting, pushing images and publishing happen in a release run, or in `mode=publish` on a tag, which is refused anywhere else.
- **PyPI by trusted publishing, one package at a time.** The wheels are built and uploaded as artifacts, attached and attested by their own job, checked in a job that needs no approval (twine, the attestations, and PyPI's copy of any file, which must be the same file), and published by `pypa/gh-action-pypi-publish`, which makes PyPI's own attestations (PEP 740). The publishing job is a matrix that runs one leg at a time, in the plan's order (`STAGES`: `lattice-core-ai` and `evalr`; then `artifactr-ai`, `reflexr` and `grantr`; then `relayr-ai`; then `portalr`), and stops at the first failure (`fail-fast`), so a later package never goes out after an earlier one failed. Each leg also verifies the attestation of its files again (the repository, the workflow, this run's commit and ref, and the file's own digest), and fails unless PyPI serves every package before it in the release (`scripts/pypi.py require`), then waits until PyPI serves its own files with the hashes built before it ends. PyPI is read through its simple index, which installers use, not its JSON API, which can lead the index or be cached as missing. A test holds the stages to the packages' own requirements.
- **Nothing is published until the maintainer says so, twice.** The repository variable `PYPI_PUBLISH` must be `true`, and the `pypi` environment's required reviewers approve each leg: seven approvals, in order. Without the variable a release run still builds, attests and attaches, and its PyPI check says what it would do.
- **`dev0` floors in the first wheels.** Every library requires `lattice-core-ai>=0.1.0.dev0`, which a published `0.1.0` satisfies. Raising the floors to the published version is the next release's (#213).
- **A dispatch on a tag runs the workflow file as it was at that tag.** A release tagged before this change cannot be run again by dispatch; the first release is the first with the dispatch.

## What the maintainer does, once

On PyPI, for each of `lattice-core-ai`, `evalr`, `artifactr-ai`, `reflexr`, `grantr`, `relayr-ai` and `portalr` (the names are free today), add a *pending* trusted publisher: owner `alexnodeland`, repository `lattice`, workflow `release.yml`, environment `pypi`. On GitHub:

- create the `pypi` environment with required reviewers (the maintainer);
- restrict its deployment branches and tags to **selected tags**, `*-v*`, and not branches; and add a tag ruleset so that only maintainers can create `*-v*` tags. This matters because PyPI's trusted publisher cannot pin a ref. A user with write access can dispatch the workflow on a branch, or push a tag by hand, and GitHub then runs *that ref's* copy of `release.yml`, which can leave out the plan and the `PYPI_PUBLISH` variable; the environment's reviewers and its tag restriction are then all that stand between that run and PyPI;
- set the repository variable `PYPI_PUBLISH` to `true`, when ready.

None of this is in the repository, and none was done when this was written.

To rehearse: run `gh workflow run release.yml --ref main` (rehearse is the default) and read the run: it builds every wheel at `main`'s head and prints the order and what PyPI has. It writes nothing.

## Options considered

| Option | For | Against |
|---|---|---|
| **Refuse a release whose commit isn't the run's (chosen)** | Provenance always names the right commit | The release exists with no wheels until the workflow is run on the tag |
| Verify against the tag's commit afterwards | No refusal | Every consumer must; the failure comes after the release |
| Build in a workflow dispatched on the tag, always | Always right | A new trigger, and it must not publish from an arbitrary dispatch |
| Publish with an API token | No environment on PyPI | A long-lived secret; against the repository's no-external-secrets stance |
| Publish all wheels at once | Simpler | A wheel can be on PyPI before what it requires |
| A job per stage | Parallel within a stage | Four copies of the job, and a failure of one stage doesn't stop the next one's `if` without a gate on every earlier job |
| A reusable workflow for the stages | No copies | Trusted publishing names the calling workflow, and the reusable one's name is not what PyPI checks; not tried |

## Consequences

- Easier: the first release can be rehearsed in full without publishing, and a wrong-commit release can't ship a wheel with the wrong provenance.
- Harder: a release created on a later push needs a manual run on its tag, with the commands given; and the maintainer's one-time setup is required before the first publish.
- Not tested: the publishing jobs have not run, and cannot be run without publishing. The plan and the PyPI checks are tested offline against fakes, the workflow's permissions and the publishing matrix are tested against the file, and it passes actionlint and zizmor. `scripts/verify-attestation` has been shell-checked and not run, since only a run that attests produces an attestation to verify; the rehearsal does not reach it, and the first release is its first run.
- Revisit: when the first release is out, #213; PEP 740 attestations are PyPI's; a `testpypi` rehearsal would need a second set of pending publishers, and isn't done.
