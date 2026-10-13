# ADR-0017: CI installs its toolchain from a cache, with retries

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland
**Amends:** [ADR-0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md): how every job installs its tools

## Context

Every job that runs moon, uv or Bun installed them through `moonrepo/setup-toolchain`, with `auto-install: true`. The action downloads proto's install script from GitHub on every run, and the script downloads proto, at its latest version, with one try. Only proto's tools and plugins are cached, never proto itself. On 2026-10-12 several jobs failed when one of those downloads answered `504`, and passed on a rerun ([lattice #96](https://github.com/alexnodeland/lattice/issues/96)). A transient failure of a download nothing in the change touched failed a required check.

## Decision

- **Every job installs its tools through `.github/actions/toolchain`,** a composite action of lattice's own, in place of `moonrepo/setup-toolchain`.
- **proto is pinned,** as `proto = "..."` in `.prototools`. Renovate moves it with a custom manager, as it does tofu and tflint.
- **`~/.proto` is cached whole:** proto, its tools and its plugins, keyed by the runner's system and architecture and by `.prototools` and the tool plugins lattice keeps. A job that finds the cache downloads nothing.
- **What isn't cached is downloaded with retries.**
  - proto comes from its GitHub release, with `curl`'s retries, five of them, on every error. Its archive is checked against the release's checksum.
  - `proto install` is retried three times, longer apart each time.
- **zizmor checks the action too,** in CI and in the hooks. Its `self-repository` audit is off: it asks for `uses: $/...`, which actionlint doesn't accept yet.

## Options considered

| Option | For | Against |
|---|---|---|
| **An action of lattice's own: proto pinned, `~/.proto` cached, downloads retried (chosen)** | A job with a cache downloads nothing; one without retries each download | An action to keep, of about 40 lines |
| setup-toolchain, with its cache | Nothing to keep | It downloads its script and proto on every run regardless, and its cache never holds proto |
| setup-toolchain, run again when it fails | Nothing to write | A second step that runs only after a failure, in every job; the first failure still shows |
| A runner image with the tools in it | Nothing downloaded at all | An image to build, host and keep current |

## Consequences

- Easier: a job that finds the cache installs nothing over the network, and one that doesn't survives a transient failure.
- Easier: every job runs the same proto, and Renovate moves it.
- Harder: lattice keeps an action and a script that setup-toolchain kept before.
- Revisit: the `self-repository` audit, once actionlint accepts `$/`.
