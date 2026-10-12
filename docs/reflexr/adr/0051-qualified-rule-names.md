# ADR-0051: Qualified rule names

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0006](0006-rules-as-typed-serializable-data.md), a rule's name, and [ADR-0031](0031-the-reference-implementations-events-and-rules.md), oncall's rule names. Decided on [RFC-0003](../rfcs/0003-managing-rules-at-runtime.md).

## Context

A rule's name keys everything reflexr keeps about it: its progress, scope states, runs, dead letters, firing ids and facts. Names were flat, and every rule was registered in code, so the application owned all of them.

RFC-0003 adds stored rules, installed in a workspace at runtime. Their names come from tenants, so they could take a name a later deploy needs, or one a code rule already has. [ADR-0039](0039-namespaced-event-types.md) had just qualified every event type with its owner's namespace (`oncall:deploy.completed`) for the same kind of clash.

## Decision

- **Every rule name is qualified, code rules included:** a namespace, a `:` and a name, at most 100 characters, matching `^[a-z][a-z0-9_]*:[a-z0-9][a-z0-9._-]*$`. oncall's rules are `oncall:triage`, `oncall:runbook` and `oncall:silence`, and a stored rule is named like `chat:prod-deploy-failures`.
- **`reflexr` is reserved.** No rule, code or stored, may use it.
- **Code rules use the application's namespaces, and stored rules the configuration's** ([ADR-0053](0053-stored-rules-one-fixed-configuration.md)). `Workspaces` refuses a code rule in a stored-rule namespace, so the two can never share a name.
- **Rule namespaces aren't event namespaces,** though they can share a word.
- **A clean break.** A renamed rule is a new rule: it starts as its `start` says, and the executor cancels the old name's unfinished runs, as it does for any rule no longer registered. There is no migration, since only the application knows its names, and nothing is released.

## Options considered

| Option | For | Against |
|---|---|---|
| One flat name space, with clashes refused | Nothing renamed | A tenant can take a name a later deploy needs |
| Qualified stored names, bare code rules | Nothing renamed | Two grammars for rule names |
| **Every rule name qualified, code rules included (chosen)** | Symmetric with ADR-0039, and a clash is impossible, since stored namespaces are the configuration's | Every code rule is renamed |
| A stored rule overrides the code rule of the same name | Tenants can tune a rule | The code rule quietly stops running |

## Consequences

- Easier: a rule's owner is in its name, on spans, in Langfuse, in metrics and in the log, as an event type's is.
- Easier: stored and code rules can't collide, so neither can shadow the other.
- Harder: every code rule was renamed once, and lost its state and unfinished runs, before the first release. Span names, Langfuse traces and `rule:` tags, and LiteLLM metadata carry the new names.

## Action items

1. [x] Qualified rule names, with the code rules renamed in oncall, the tests, the fixtures and the docs (alexnodeland/reflexr#83).
