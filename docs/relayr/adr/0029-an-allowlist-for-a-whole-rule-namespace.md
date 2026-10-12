# ADR-0029: An allowlist for a whole rule namespace

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland
**Amends:** [ADR-0020](0020-allowlists.md): allowlists were keyed by a rule's name alone

## Context

Rules drafted in chat are installed at runtime, under names no one can list in advance, in the namespaces reflexr's `StoredRules` allows, such as `chat`. Their first action posts a notice in a thread the drafter named, which isn't in their chain. `Outbound(allowlists=...)` looked a rule's allowlist up by its exact name, so these rules could only have the default, which allows notices in the chain's threads alone.

## Decision

- **A key of `Outbound(allowlists=...)` may name a whole namespace,** as `"chat:*"`. It applies to every rule in that namespace that has no allowlist of its own; a rule's own name comes first.
- **That is the only wildcard.** `Outbound` checks every key when it is made: a key is a rule's name, as reflexr names rules, or `<namespace>:*`. Anything else is refused, `reflexr`'s reserved namespace included: no globbing within a name, and no wildcard across namespaces.
- **Phase 5b, rules from chat in stackr's template,** is to give `chat:*` `Allowlist(threads="any")`: notices in any thread, and nothing more.

## Options considered

| Option | For | Against |
|---|---|---|
| **A namespace's key, after the rule's own (chosen)** | Plain data still; one line covers every rule a namespace will hold | A rule in the namespace gets what the namespace has, unless named |
| Patterns over names | Finer grouping | Matching rules no one reviews by name |
| A callback from the rule to its allowlist | Anything can decide | The limit moves into code, as ADR-0020 rejected |

## Consequences

- Easier: rules installed at runtime get an allowlist from their namespace, reviewed with the application's code.
- Harder: every rule in the namespace gets what the namespace's allowlist grants, so it should grant only what all of them need.
