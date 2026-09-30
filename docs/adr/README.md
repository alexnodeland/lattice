# Architecture decision records

Each record captures one decision about the family as a whole: the context that forced it, the options considered, and the consequences we accepted. Records are immutable once accepted; a changed decision gets a new record that amends or supersedes the old one. A decision about one package is recorded in that package's own series, in `docs/<package>/adr/`. The proposal that made lattice is [stackr RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md), and these records begin with what its move decided that the RFC's design didn't.

Outside its own series, a record is named with its package, as in "reflexr ADR-0003", and these as "lattice ADR-0002".

| ADR | Title | Status |
|---|---|---|
| [0002](0002-ci-runs-every-affected-project-and-its-dependents.md) | CI runs every affected project and its dependents | Accepted |
| [0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md) | CI on pull requests, Nightly on main, and a required Title check | Accepted |
| [0004](0004-one-github-app-for-release-please-and-renovate.md) | One GitHub App for release-please and Renovate | Accepted |
| [0005](0005-renovate-runs-in-lattices-own-actions.md) | Renovate runs in lattice's own Actions | Accepted |
| [0006](0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md) | release-please: first versions, pre-1.0 bumps, and what releases | Accepted |
| [0007](0007-a-timeout-on-every-test-and-every-job.md) | A timeout on every test and every job | Accepted |
| [0008](0008-one-resolution-litellm-held-at-1-83-0.md) | One resolution, with litellm held at 1.83.0 | Accepted |
| [0009](0009-one-dev-container-at-the-root.md) | One dev container, at the root | Accepted |

To add a record, copy [`template.md`](template.md) to the next number and add a row above.
