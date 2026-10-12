# ADR-0030: Drift proposed back to a rule's artifact

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0028](0028-rules-from-chat.md): how relayr finds the rule an artifact installed

Builds the last of phase 5 of [RFC-0001](../rfcs/0001-v0.1-implementation-plan.md): [ADR-0005](0005-where-a-rules-source-of-truth-lives.md)'s drift, proposed back.

## Context

A rule drafted in chat has two records: its artifact, which people reviewed, and the stored rule reflexr runs ([ADR-0005](0005-where-a-rules-source-of-truth-lives.md)). An operator, or anyone allowed to manage rules in reflexr, can update or archive the stored rule directly. ADR-0005 has relayr propose that change to the artifact, so the two don't drift apart silently.

[ADR-0028](0028-rules-from-chat.md) found the rule an artifact installed by the stored rule's current provenance. A change made directly sets provenance of its own, so after one, relayr would no longer find the rule. Provenance is also a claim anyone allowed to install can make.

## Decision

- **relayr knows a rule from chat by its own facts.** reflexr logs a `reflexr:rule_installed` fact for every install and update, naming the run that made it. The installs `relayr:rules-from-chat` made, with their provenance, say which rule each artifact installed, and which artifact each rule came from. This replaces ADR-0028's lookup by the current provenance, and its scan of every stored rule. A change made directly can't hide a rule from its artifact, and an install no run of relayr's made can't claim one.
- **A second code rule, `relayr:rule-drift`,** fires on `reflexr:rule_installed` and `reflexr:rule_archived`, scoped by the rule.
  - It passes over relayr's own changes, which came from the artifact.
  - It also passes over a rule no draft installed, and one whose artifact is archived.
  - **An update** is proposed as an edit of the artifact's `/rule` to the new version, unless the artifact holds it already.
  - **An archive** is proposed as archiving the artifact.
  - Its rationale says the rule was changed in reflexr, outside its artifact.
- **The proposal goes to the thread the rule was drafted in:** that of the proposal relayr installed it from. relayr's allowlists give `relayr:rule-drift` any thread (`ALLOWLISTS`), and the application merges them into its own.
- **Accepting puts the two in step again.** An accepted edit updates the rule from the artifact, through `relayr:rules-from-chat`, as any accepted change does. An accepted archive archives the artifact, and its rule is archived already. Rejecting leaves reflexr's version running, and the artifact as people reviewed it.
- **The outbound adapter can archive.** `RunActions.archive(artifact_id)` proposes archiving an artifact, unless the allowlist lets the rule edit its kind directly. Its proposal id is derived, as for every write ([ADR-0019](0019-runs-act-once-through-derived-ids-and-keyed-edits.md)), and an archived artifact is skipped.

## Options considered

| Option | For | Against |
|---|---|---|
| **A drift rule on reflexr's facts (chosen)** | In the log, in order, retried as any run is | One more code rule for the application to run |
| A periodic comparison of every rule with its artifact | Catches anything | A schedule, and a scan of every workspace |
| **The rule an artifact installed, from relayr's own facts (chosen)** | No claim of provenance decides it, and no scan of every stored rule | A read of the log's install facts |
| From the stored rule's current provenance | One read | Lost after a direct change, and claimable by anyone who may install |

## Consequences

- Easier: a rule changed or stopped by an operator shows up in the thread it came from, as a proposal people can accept or reject.
- Harder: until someone accepts or rejects it, the artifact and the running rule differ.
