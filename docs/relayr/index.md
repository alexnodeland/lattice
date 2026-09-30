---
title: relayr
description: The planned bridge between artifactr and reflexr, through which events from chats and artifacts become events for rules, and runs act back in the chat as proposals and notices.
hide:
  - navigation
---

<div class="relayr-hero" markdown>

<h1 class="relayr-visually-hidden">relayr</h1>

![relayr](assets/brand/lockup-light.svg#gh-light-mode-only)
![relayr](assets/brand/lockup-dark.svg#gh-dark-mode-only)

The planned bridge between artifactr and reflexr: events from chats and artifacts will become events for rules, and runs will act back in the chat as proposals and notices.

</div>

!!! note "Planned, not yet usable"

    relayr's foundation is done: the package, its tooling, its decisions and its [v0.1 plan](rfcs/0001-v0.1-implementation-plan.md). The package holds only its version so far, and everything below describes what the plan's phases build. It is distributed as `relayr-ai`, since the name `relayr` on PyPI is an unrelated project, and imported as `relayr`.

## Why: one bridge, built once

An application can mount [artifactr](../artifactr/index.md) and [reflexr](../reflexr/index.md) side by side, on one database and one telemetry setup, over one shared context: the same tenant and workspace ids name the same context in both. But the two halves don't talk to each other. A rule can't see what people say in a thread, and a run can't put its result in front of the people it concerns. Each application that wants this would write its own glue, and meet the same hard parts: duplicate and lost deliveries, rules that trigger themselves, two kinds of session that don't line up, and events that anyone could forge.

[stackr's RFC-0002](../stackr/rfcs/0002-the-combined-system.md) designs the bridge once, and relayr is where it is built. It will use only the two libraries' public APIs, and neither library will import it or the other.

## What it will do

- **Inbound: chats and artifacts become events.** One follower per workspace, with a lease, a cursor and dead letters, publishes selected artifactr events into reflexr under the `artifactr` namespace, such as `artifactr:message_posted`, `artifactr:artifact_changed` and `artifactr:proposal_resolved`, so that a message fires a rule exactly once, across a restart and a redelivery ([ADR-0006](adr/0006-bridged-types-in-the-artifactr-namespace.md)).
- **Outbound: runs act as participants.** A pydantic-ai capability and helpers let a run act in artifactr as its rule's own external agent, `reflexr:<rule>`, so artifactr's rules apply to it: under a `propose` write policy its edits are proposals, and relayr never resolves one ([ADR-0002](adr/0002-the-outbound-actor-an-external-agent-per-rule.md)).
- **Notices by default.** A rule's messages start no turn in the thread, unless the rule's allowlist grants it ([ADR-0007](adr/0007-notices-by-default.md)).
- **Chains and sessions kept apart, and linked.** A thread is never a causal chain, and a chain never joins a thread's session or model history; traces are linked, and Langfuse sessions tagged, across the two ([ADR-0003](adr/0003-a-thread-is-never-a-chain.md), [ADR-0004](adr/0004-sessions-linked-not-continued.md)).
- **Rules from chat.** A rule drafted in a thread is a `rule` artifact, reviewed as a proposal, and goes live in reflexr's stored rules only when a person accepts it, with provenance recorded both ways ([ADR-0005](adr/0005-where-a-rules-source-of-truth-lives.md)).
- **Evaluation.** Proposal outcomes become feedback on the runs that proposed them, with measures of acceptance, rewrites and time to resolution.
- **A ledger of its own**, in memory or in SQL, behind the `sql`, `sqlite` and `postgres` extras.

[RFC-0001](rfcs/0001-v0.1-implementation-plan.md#phases) builds these in seven phases after the foundation, and says what each waits on in the libraries. Its guides, reference and architecture come with the phases that build what they describe.

## Where to go next

| If you want to | Read |
|---|---|
| Understand why each part will be the way it is | The [decision records](adr/README.md) |
| See the plan, its phases and what each waits on | [RFC-0001](rfcs/0001-v0.1-implementation-plan.md), and the [RFCs](rfcs/README.md) |
| Read the design relayr builds | [stackr's RFC-0002](../stackr/rfcs/0002-the-combined-system.md) |
| Use the mark and its colours | The [brand page](assets/brand/README.md) |
| See what has changed | The [changelog](project/changelog.md) |
| Contribute | [Contributing](../project/contributing.md) |
