# Architecture decision records

Each record captures one decision about the family as a whole: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. A decision about one package is recorded in that package's own series, in `docs/<package>/adr/`. The proposal that made lattice is [stackr RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md), and these records begin with what its move decided that the RFC's design didn't.

Outside its own series, a record is named with its package, as in "reflexr ADR-0003", and these as "lattice ADR-0002".

| ADR | Title | Status |
|---|---|---|
| [0001](0001-lattices-brand.md) | lattice's brand | Accepted, amended by [0014](0014-portalrs-and-grantrs-marks.md) |
| [0002](0002-ci-runs-every-affected-project-and-its-dependents.md) | CI runs every affected project and its dependents | Accepted, amended by [stackr ADR-0018](../stackr/adr/0018-the-template-pins-the-libraries-at-its-own-commit.md) |
| [0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md) | CI on pull requests, Nightly on main, and a required Title check | Accepted, amended by [0012](0012-title-checks-the-breaks-in-the-public-apis.md), [0016](0016-a-merge-queue-on-mergify.md) and [0017](0017-ci-installs-its-toolchain-from-a-cache-with-retries.md) |
| [0004](0004-one-github-app-for-release-please-and-renovate.md) | One GitHub App for release-please and Renovate | Accepted |
| [0005](0005-renovate-runs-in-lattices-own-actions.md) | Renovate runs in lattice's own Actions | Accepted |
| [0006](0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md) | release-please: first versions, pre-1.0 bumps, and what releases | Accepted |
| [0007](0007-a-timeout-on-every-test-and-every-job.md) | A timeout on every test and every job | Accepted |
| [0008](0008-one-resolution-litellm-held-at-1-83-0.md) | One resolution, with litellm held at 1.83.0 | Accepted |
| [0009](0009-one-dev-container-at-the-root.md) | One dev container, at the root | Accepted |
| [0010](0010-every-projects-tests-run-in-a-random-order.md) | Every project's tests run in a random order | Accepted |
| [0011](0011-codeql-and-scorecard.md) | CodeQL on every change, and Scorecard every week | Accepted |
| [0012](0012-title-checks-the-breaks-in-the-public-apis.md) | The Title check holds each break in a public API to its marking | Accepted |
| [0013](0013-pyright-stays-until-ty-can-replace-it.md) | pyright stays until ty can replace it | Accepted |
| [0014](0014-portalrs-and-grantrs-marks.md) | portalr's and grantr's marks | Accepted |
| [0015](0015-acceptance-tests-against-the-reference-applications.md) | Acceptance tests against the reference applications | Accepted, amended by artifactr 0061 and 0063, and reflexr 0060 and 0061 |
| [0016](0016-a-merge-queue-on-mergify.md) | A merge queue on Mergify | Accepted |
| [0017](0017-ci-installs-its-toolchain-from-a-cache-with-retries.md) | CI installs its toolchain from a cache, with retries | Accepted |
| [0018](0018-lattice-core-what-the-libraries-share.md) | lattice-core, what the libraries share | Accepted, amended by [0020](0020-the-telemetry-contract-needs-no-extra.md) and [0021](0021-the-refusal-schema-needs-no-extra.md) |
| [0019](0019-a-tag-for-each-tenants-workspace.md) | A tag for each tenant's workspace | Accepted |
| [0020](0020-the-telemetry-contract-needs-no-extra.md) | The telemetry contract needs no extra | Accepted |
| [0020](0020-the-telemetry-contract-needs-no-extra.md) | The telemetry contract needs no extra | Accepted |
| [0021](0021-the-refusal-schema-needs-no-extra.md) | The refusal schema needs no extra | Accepted |
| [0022](0022-litellm-requests-carry-the-propagated-trace-tags.md) | LiteLLM requests carry the propagated trace tags | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above. Each package's series uses the same template.
