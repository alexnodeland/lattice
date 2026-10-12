# ADR-0020: Allowlists

**Status:** Accepted, amended on 2026-10-12: a namespace's allowlist, below
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

artifactr checks a rule's writes to artifacts and proposals against their write policies and the thread's mode, but not where a rule acts, whether it creates threads, or whether its message starts a turn. [stackr RFC-0002][rfc-0002-security] makes each rule's allowlist the limit on those, "required rather than optional", defaulting to proposals and notices in the chain's own thread, and [D7](0007-notices-by-default.md) makes starting a turn a per-rule permission.

## Decision

- **`Allowlist`** is a frozen model with four fields: `direct`, the artifact kinds a rule creates and edits without proposing; `threads`, `chain` or `any`; `create_threads`; and `turns`. artifactr's write policy and the thread's mode still apply to a direct write.
- **Every rule has one.** `Outbound(allowlists=...)` maps rule names to allowlists; a rule with none gets the default, which allows proposals and notices only.
- **A chain's threads** are the threads of the bridged events that made the rule fire, and those its run creates. A write names a thread or takes the first of them; with `threads="chain"`, any other thread is refused. A run with none must create one (if allowed) or name one (with `threads="any"`).
- **`send` also needs a runner:** `Outbound(runner=...)`, artifactr's `Runner`, which starts the turn. Without one no rule may start turns.
- **A refusal is `NotAllowed`,** a permanent `RunFailure` with the reason `not_allowed`. An agent's tools turn it into a retry for the model, which can do something else.

## Options considered

| Option | For | Against |
|---|---|---|
| **A mapping from rule names, with a restrictive default (chosen)** | Plain data, reviewed with the rules; a rule nobody listed can do the least | Stored rules need their allowlist from somewhere: phase 5 decides where |
| A callback per write | Anything can be checked | The limit moves into code no one reviews with the rule |
| A permissive default | Nothing to configure | A new rule could start turns, or act in any thread, by omission |

## Consequences

- Easier: what each rule may do beyond proposals and notices is one line beside it.
- Harder: phase 5's chat rules need an allowlist of their own; the amendment below gives one to their namespace.

## Amendment (2026-10-12): a namespace's allowlist

Rules drafted in chat are installed at runtime, under names no one can list in advance, in the namespaces reflexr's `StoredRules` allows, such as `chat`. Their first action posts a notice in a thread the drafter named, which their chain doesn't hold.

- **A key of `Outbound(allowlists=...)` may name a whole namespace,** as `"chat:*"`. It applies to every rule in that namespace that has no allowlist of its own; a rule's own name comes first.
- **That is the only wildcard.** Any other key with a `*` is refused when `Outbound` is made: no globbing within a name, and no wildcard across namespaces.
- **stackr's template** gives `chat:*` `Allowlist(threads="any")`: notices in any thread, and nothing more.

| Option | For | Against |
|---|---|---|
| **A namespace's key, after the rule's own (chosen)** | Plain data still; one line covers every rule a namespace will hold | A rule in the namespace gets what the namespace has, unless named |
| Patterns over names | Finer grouping | Matching rules no one reviews by name |
| A callback from the rule to its allowlist | Anything can decide | The limit moves into code, as the original decision rejected |

[rfc-0002-security]: ../../stackr/rfcs/0002-the-combined-system.md#security
