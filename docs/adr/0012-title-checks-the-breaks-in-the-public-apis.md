# ADR-0012: The Title check holds each break in a public API to its marking

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) runs `griffe check` against each package's last release tag, and fails a break "unless the pull request marks it with `!` or `BREAKING CHANGE`". release-please reads that marking from the squash commit: its title is the pull request's title, and its body the description ([ADR-0006](0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)).

Three things the RFC doesn't settle:

- **A break stays a break until the next release.** artifactr's `main` already has 14 breaks against `artifactr-v0.1.0`. Checked plainly against the tag, every later pull request that touches artifactr, even a typo fix, would fail until the next release.
- **Most packages have no release in lattice.** Only artifactr has a tag, `artifactr-v0.1.0`; evalr, reflexr and relayr are at `0.0.0` in the manifest.
- **griffe compares an attribute's value as text.** Of those 14 breaks, 8 are `Attribute value was changed`. Seven break no caller: a union with a new member (`Actor`, `Command`, `Event`, `KnownEvent`, `Note`), an edited string (`INSTRUCTIONS`), and an attribute's initial value (`ArtifactrMcp.server`). One does: `ResolveClient`, a type alias whose parameter changed type.

The marking lives in the title and the description, which CI's jobs never rerun for when they are edited ([ADR-0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md)).

## Decision

- **A pull request answers for the breaks it adds.** [`scripts/api.py`](https://github.com/alexnodeland/lattice/blob/main/scripts/api.py) compares each package with its last release, its newest `<name>-v*` tag on the base branch, through griffe's library: once as the pull request's merge commit has it, and once as the base branch has it. A break the merge commit has and the base doesn't is the pull request's, and it fails unless the title has `!` after its type or scope, or the description has a `BREAKING CHANGE:` footer. Each break is an annotation on the file and line. A break that is reverted before the release adds nothing.
- **A package with no release tag is skipped,** with a message saying so. It has no published API to keep, and its first release starts the comparison.
- **`Attribute value was changed` isn't counted.** Every other kind griffe reports is: removed objects, changed kinds, removed bases, and added, removed, reordered or newly required parameters.
- **The Title check runs it,** as a step after the title's own check. Title already reruns when the title or the description is edited, and is already required. So Title now says that the title is a Conventional Commit, and marks every break that the pull request makes.
- **`moon run lattice:api`** runs the same comparison locally against `origin/main`, with no marking, to show what a branch would have to mark.

## Options considered

### What a pull request answers for

| Option | A pull request after a marked break |
|---|---|
| **The breaks it adds to the base's (chosen)** | Passes, unless it breaks something else |
| Every break against the tag (RFC-0003, read plainly) | Fails until the next release, whatever it changes |
| Every break against the base branch | Passes, but a break and its revert each count, and the tag plays no part |

### Where it runs

| Option | Edited title or description | Required |
|---|---|---|
| **A step in Title (chosen)** | Checked again | Yes |
| A job in CI | Keeps its old result | Yes |
| A workflow of its own | Checked again | Only once the ruleset names it |

### Attribute values

| Option | What it costs |
|---|---|
| **Not counted (chosen)** | A type alias narrowed, as `ResolveClient`'s parameter was, goes unflagged |
| Counted | A widened union or an edited string needs `!`, which bumps the version and calls it breaking in the changelog |

## Trade-off analysis

Comparing with the base keeps the RFC's comparison with the release, so what is checked is what users of the last release would see, while charging each pull request only for its own breaks. Leaving out value changes trades a rare missed break in a type alias for no false ones, which would otherwise teach everyone to mark breaks that aren't.

## Consequences

- Easier: an unmarked break fails the pull request that makes it, with the file and line, before release-please writes a minor bump that should have been a breaking one.
- Harder: the Title check checks out the repository and installs the root's tools, so it takes about half a minute instead of seconds.
- Harder: a change to a type alias is a break that the author must still mark by judgement.
- evalr, reflexr and relayr are checked from their first release.
- This amends [ADR-0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md): Title checks the title and what it must mark.
