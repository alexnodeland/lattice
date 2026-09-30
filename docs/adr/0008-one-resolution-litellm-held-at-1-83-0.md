# ADR-0008: One resolution, with litellm held at 1.83.0

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#the-uv-workspace) gives the family one `uv.lock`, so every package must agree on every third-party range, and said they did. The rehearsal found they resolve together at one cost. evalr's `[dspy]` extra brings DSPy, and DSPy brings litellm. Every litellm after 1.83.0 pins `openai<3`, while the libraries' extras bring `pydantic-ai-slim[openai]`, which needs `openai>=3.19`. In one resolution, uv settles on litellm 1.83.0.

That version has 13 advisories, all in litellm's proxy server. lattice never runs it: it installs litellm only as DSPy's SDK, through evalr's `[dspy]` extra and docplan's. stackr's gateway runs LiteLLM's own image, pinned in its `compose.yaml`, not this package. osv-scanner reports two more things that don't apply: diskcache 5.6.3, which DSPy uses, unpickles what its cache directory holds, and no fixed version exists; and a package on PyPI named `oncall`, unrelated to lattice's example, matches its name.

## Decision

- **One resolution stands, with litellm at 1.83.0,** until litellm allows openai 3 or DSPy stops depending on litellm.
- **`osv-scanner.toml`, beside `uv.lock`, records each advisory that doesn't apply,** with why, and an `ignoreUntil` of 2026-12-31 by which it is reviewed again: litellm's 13 and diskcache's. The `oncall` collision is a package override, with no date. CI's OSV job and Nightly's scan both read the file.
- **GitHub's Dependabot alerts for the same advisories are dismissed with the same reasons,** so the two lists agree.
- **[#17](https://github.com/alexnodeland/lattice/issues/17) tracks lifting the ignores** by that date: lift them when a fix lets the lock move, or extend them with the reason.

## Options considered

| Option | One environment with every package and extra | The advisories |
|---|---|---|
| **One resolution, litellm at 1.83.0, the advisories recorded (chosen)** | Yes | In code lattice never runs; each recorded, with a date to review it |
| Separate resolutions for the extras that meet here | No: `--all-extras` no longer installs together, which CI and the docs build need | None where DSPy runs |
| Override litellm's `openai<3` | Yes | None, but litellm runs on an openai it says it can't |
| Drop DSPy from the workspace | Yes | None, and evalr's DSPy judges go untested |

## Consequences

- Easier: one environment holds every package with every extra, as the docs build and CI need, and the scans stay clean without hiding anything unexplained.
- Harder: this is one resolution's drawback, as RFC-0003 foresaw: one package's dependency holds everyone's litellm back.
- Harder: the ignores lapse on 2026-12-31, and a scan then fails until someone reviews them.
