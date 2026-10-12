# ADR-0020: Allowlists

**Status:** Accepted
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
- Harder: phase 5's chat rules need an allowlist of their own, which the install rule will set.

[rfc-0002-security]: ../../stackr/rfcs/0002-the-combined-system.md#security
