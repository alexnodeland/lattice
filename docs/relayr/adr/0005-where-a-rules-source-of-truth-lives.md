# ADR-0005: Where a rule's source of truth lives

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Records decision D5 of [stackr RFC-0002][rfc-0002], the combined system.

## Context

A rule drafted in a thread is a `rule` artifact: a reflexr `Rule` as JSON, reviewed as a proposal before it goes live. Once accepted, relayr installs it in reflexr's stored rules ([reflexr RFC-0003][r-rfc-0003]). The same rule then exists in two places, and one of them has to be the record.

## Decision

- **The artifact is the reviewed record**: drafted, discussed, changed and archived where people work.
- **reflexr's stored rules hold the running definition**, installed through reflexr's API.
- **Provenance goes both ways.** Each installed version records the artifact, its version, the proposal and who approved it.
- **Drift is proposed back.** If the rule is changed in reflexr directly, for example by an operator, relayr proposes the same change to the artifact, so the two don't drift apart silently.

## Options considered

| Option | For | Against |
|---|---|---|
| **The artifact for review, reflexr's store for running, with provenance both ways (chosen)** | Reviewed and discussed where people work, and run where rules run | Two records to keep in step, so drift has to be detected |
| reflexr's store only; the artifact is a draft, archived once installed | One record | No review trail in the workspace, and people can't see or change a live rule from chat |
| The artifact only; reflexr reads rules from artifactr | One record | reflexr would depend on artifactr at runtime, against reflexr ADR-0003 |

## Consequences

- Easier: every live rule has a reviewed record that people can read and change in chat.
- Harder: relayr has to notice changes made in reflexr and propose them back.
- This is phase 5's work, and waits on reflexr's runtime rule management.

[r-rfc-0003]: https://github.com/alexnodeland/reflexr/blob/main/docs/rfcs/0003-managing-rules-at-runtime.md
[rfc-0002]: https://github.com/alexnodeland/stackr/blob/main/docs/rfcs/0002-the-combined-system.md#d5-where-a-rules-source-of-truth-lives
