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
- **A release is built from the commit it was tagged at, or not at all (#206).** If release-please's `--sha` for any released package, stackr included (its images are attested the same way), is not the run's commit, the plan fails before anything is built. Its message gives the command to run the workflow again on the tag, where the two are the same, and says what that command does: for a wheel, it attaches and attests the wheels and publishes to PyPI only if `PYPI_PUBLISH` is true, after the `pypi` environment's approval; for stackr, it builds the images again, pushes them and adds them to the release's notes, and PyPI is not in it. The cost is accepted: a release created on a later push exists with no wheels until someone runs it. A released package without a full commit, or a tag whose version is not its pyproject's, is refused too.
- **A release run never publishes to PyPI. Publishing is by dispatch on a tag, one package a dispatch** (decided by the user). Merging the release pull request creates the tags and the GitHub releases, and the run it triggers builds, attests and attaches the wheels, pushes stackr's images, and lists in its summary the seven commands that publish, in dependency order: `gh workflow run release.yml --ref <tag> -f tag=<tag> -f mode=publish`. Each dispatch publishes that package, in a job gated by the `pypi` environment, so each is one approval, one at a time. The order is `lattice-core-ai` and `evalr`; then `artifactr-ai`, `reflexr` and `grantr`; then `relayr-ai`; then `portalr` (`STAGES`, held by a test to the packages' own requirements).
- **A dispatch publishes only what PyPI can already satisfy.** Before it publishes, the job verifies the attestation of its files again (the repository, the workflow, this run's commit and ref, and the file's own digest), and fails unless PyPI serves, at the version this repository has at the tag, every other package of this repository that the package requires, read from its pyproject whether or not it is in this release. Then it publishes with `pypa/gh-action-pypi-publish` (PyPI's own attestations, PEP 740) and waits until PyPI serves its files with the hashes built. PyPI is read through its simple index, which installers use, not its JSON API, which can lead the index or be cached as missing, with a few tries for a PyPI that errs.
- **A rehearsal writes nothing, anywhere.** `mode` is `rehearse` unless it says `publish`. A rehearsal, on a branch (every wheel at its head) or on a tag (that release, again), builds and checks, and attaches nothing to a release, attests nothing, pushes no image, rewrites no release notes and publishes nothing. It keeps the files it built as artifacts of the run, and nothing else. This is structural: the build job's permissions are `contents: read`, and the jobs that can write (`attach`, `publish-images`, `release-notes`, `pypi-publish`) run only where the plan writes or publishes; tests hold both, and which jobs may ask for an identity token. `mode=publish` is refused anywhere but on a tag.
- **A file attached to a release is never replaced.** A run on a tag builds the wheel again; `scripts/attach-assets` leaves a file already attached with the same bytes, and fails on one with other bytes, so a rebuild that is not byte for byte the same cannot replace what the release, and PyPI if it has the file, holds. Our wheels are believed reproducible (`uv_build`, Vite and the notices are deterministic) and that is not verified; if a rebuild differs, delete the asset on purpose. The comparison uses the asset's `digest` in `gh release view --json assets`, which GitHub fills for assets uploaded since mid-2025; where it is null or absent, the script downloads the asset and sums its bytes itself. Verified read-only with gh 2.102.0: `assets[]` there carries `digest` (`sha256:<hex>`) next to `name`, `size` and `url`, on a public release of another repository (cli/cli), since this repository has no release yet; the first release here is the first check on its own assets.
- **Nothing is published until the maintainer says so, twice.** The repository variable `PYPI_PUBLISH` must be `true`, and the `pypi` environment's required reviewers approve each dispatch. Without the variable a dispatch still attaches and attests, and publishes nothing.
- **`dev0` floors in the first wheels.** Every library requires `lattice-core-ai>=0.1.0.dev0`, which a published `0.1.0` satisfies. Raising the floors to the published version is the next release's (#213).
- **A dispatch on a tag runs the workflow file as it was at that tag.** A release tagged before this change cannot be run again by dispatch; the first release is the first with the dispatch.
- **Concurrency.** A push has its own group and a dispatch has one per ref, so a dispatch cannot knock out a release run, and seven dispatches on seven tags do not queue behind each other. A run waiting for its environment's approval holds its group, so a second dispatch on the same tag waits for the first.

## What the maintainer does, once

On PyPI, for each of `lattice-core-ai`, `evalr`, `artifactr-ai`, `reflexr`, `grantr`, `relayr-ai` and `portalr` (the names are free today), add a *pending* trusted publisher: owner `alexnodeland`, repository `lattice`, workflow `release.yml`, environment `pypi`. On GitHub:

- create the `pypi` environment with required reviewers (the maintainer);
- restrict its deployment branches and tags to **selected tags**, `*-v*`, and not branches; and add a **tag ruleset** so that only maintainers can create `*-v*` tags, **with the release-please GitHub App (`alexnodeland-lattice`) as a bypass actor**: otherwise release-please cannot create the release tags. This matters because PyPI's trusted publisher cannot pin a ref. A user with write access can dispatch the workflow on a branch, or push a tag by hand, and GitHub then runs *that ref's* copy of `release.yml`, which can leave out the plan and the `PYPI_PUBLISH` variable; the environment's reviewers and its tag restriction are then all that stand between that run and PyPI;
- set the repository variable `PYPI_PUBLISH` to `true`, when ready.

None of this is in the repository, and none was done when this was written.

**To publish a release:** after the release pull request merges and its run has finished, open that run's summary and run the seven commands it lists, one at a time, in the order given, approving the `pypi` environment for each when GitHub asks. Wait for each to finish before the next: the later ones check that PyPI serves what they require, and fail if it does not. **To recover a partial release** (one dispatch failed, or was rejected): run the same command again, which skips what PyPI already has (`skip-existing`) and fails on a file PyPI has with other bytes; then go on with the commands after it. A package whose wheels were never attached (the #206 refusal) gets its wheels from its own dispatch first.

To rehearse: run `gh workflow run release.yml --ref main` (rehearse is the default) and read the run: it builds every wheel at `main`'s head and prints the order and what PyPI has. It writes nothing.

## Options considered

| Option | For | Against |
|---|---|---|
| **Refuse a release whose commit isn't the run's (chosen)** | Provenance always names the right commit | The release exists with no wheels until the workflow is run on the tag |
| Verify against the tag's commit afterwards | No refusal | Every consumer must; the failure comes after the release |
| Build in a workflow dispatched on the tag, always | Always right | A new trigger, and it must not publish from an arbitrary dispatch |
| Publish with an API token | No environment on PyPI | A long-lived secret; against the repository's no-external-secrets stance |
| Publish every wheel from the release run | No dispatches to run | A release run is also the push to main, and a failure part way leaves PyPI half published with no one deciding |
| A job per stage | Parallel within a stage | Four copies of the job, and a failure of one stage doesn't stop the next one's `if` without a gate on every earlier job |
| A reusable workflow for the stages | No copies | Trusted publishing names the calling workflow, and the reusable one's name is not what PyPI checks; not tried |

## Consequences

- Easier: the first release can be rehearsed in full without publishing, and a wrong-commit release can't ship a wheel with the wrong provenance.
- Harder: publishing is seven dispatches and seven approvals, one at a time, by hand, after every release; a release created on a later push needs a manual run on its tag first; and the maintainer's one-time setup is required before the first publish. The release run's summary lists the commands, so none is composed by hand.
- Not tested: the publishing jobs have not run, and cannot be run without publishing. The plan and the PyPI checks are tested offline against fakes, the workflow's permissions and the publishing matrix are tested against the file, and it passes actionlint and zizmor. `scripts/verify-attestation` and `scripts/attach-assets` have been shell-checked and not run, since only a run that attests produces an attestation to verify; the rehearsal does not reach it, and the first release is its first run.
- Revisit: when the first release is out, #213; PEP 740 attestations are PyPI's; a `testpypi` rehearsal would need a second set of pending publishers, and isn't done.
