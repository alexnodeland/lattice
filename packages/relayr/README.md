<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/relayr/assets/brand/banner-dark.svg">
  <img alt="relayr: the bridge between artifactr and reflexr." src="https://raw.githubusercontent.com/alexnodeland/lattice/main/docs/relayr/assets/brand/banner-light.svg" width="100%">
</picture>

<p>
  <a href="https://lattice.alexnodeland.com/relayr/"><img alt="Docs" src="https://img.shields.io/badge/docs-lattice.alexnodeland.com%2Frelayr-9E0A5E"></a>
  <a href="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml"><img alt="Nightly" src="https://github.com/alexnodeland/lattice/actions/workflows/nightly.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12, 3.13 and 3.14" src="https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-9E0A5E">
  <img alt="Coverage: 100%" src="https://img.shields.io/badge/coverage-100%25-9E0A5E">
  <img alt="Typed: pyright strict" src="https://img.shields.io/badge/typed-pyright%20strict-9E0A5E">
  <a href="https://github.com/alexnodeland/lattice/blob/main/packages/relayr/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-9E0A5E"></a>
</p>

**relayr** is the planned bridge between [artifactr](https://lattice.alexnodeland.com/artifactr/) and [reflexr](https://lattice.alexnodeland.com/reflexr/): events from chats and artifacts will become events for rules, and runs will act back in the chat as proposals and notices. It will use only the two libraries' public APIs, and neither library will import it or the other.

> **Status:** planned, not yet usable. Its foundation is done: the package, its tooling, its decisions and its [v0.1 plan](https://lattice.alexnodeland.com/relayr/rfcs/0001-v0.1-implementation-plan/). The package holds only its version so far, and everything below describes what the plan's phases build. Its distribution is `relayr-ai`, since the name `relayr` on PyPI is an unrelated project, and it is imported as `relayr`.

## Why

An application can mount artifactr and reflexr side by side, on one database and one telemetry setup, over one shared context: the same tenant and workspace ids name the same context in both. But the two halves don't talk to each other. A rule can't see what people say in a thread, and a run can't put its result in front of the people it concerns. Each application that wants this would write its own glue, and meet the same hard parts: duplicate and lost deliveries, rules that trigger themselves, two kinds of session that don't line up, and events that anyone could forge. [stackr's RFC-0002](https://lattice.alexnodeland.com/stackr/rfcs/0002-the-combined-system/) designs the bridge once, and relayr is where it is built.

## What it will do

- **Inbound: chats and artifacts become events.** One follower per workspace, with a lease, a cursor and dead letters, publishes selected artifactr events into reflexr under the `artifactr` namespace, such as `artifactr:message_posted`, `artifactr:artifact_changed` and `artifactr:proposal_resolved`, so that a message fires a rule exactly once, across a restart and a redelivery ([ADR-0006](https://lattice.alexnodeland.com/relayr/adr/0006-bridged-types-in-the-artifactr-namespace/)).
- **Outbound: runs act as participants.** A pydantic-ai capability and helpers let a run act in artifactr as its rule's own external agent, `reflexr:<rule>`, so artifactr's rules apply to it: under a `propose` write policy its edits are proposals, and relayr never resolves one ([ADR-0002](https://lattice.alexnodeland.com/relayr/adr/0002-the-outbound-actor-an-external-agent-per-rule/)).
- **Notices by default.** A rule's messages start no turn in the thread, unless the rule's allowlist grants it ([ADR-0007](https://lattice.alexnodeland.com/relayr/adr/0007-notices-by-default/)).
- **Chains and sessions kept apart, and linked.** A thread is never a causal chain, and a chain never joins a thread's session or model history; traces are linked, and Langfuse sessions tagged, across the two ([ADR-0003](https://lattice.alexnodeland.com/relayr/adr/0003-a-thread-is-never-a-chain/), [ADR-0004](https://lattice.alexnodeland.com/relayr/adr/0004-sessions-linked-not-continued/)).
- **Rules from chat.** A rule drafted in a thread is a `rule` artifact, reviewed as a proposal, and goes live in reflexr's stored rules only when a person accepts it, with provenance recorded both ways ([ADR-0005](https://lattice.alexnodeland.com/relayr/adr/0005-where-a-rules-source-of-truth-lives/)).
- **Evaluation.** Proposal outcomes become feedback on the runs that proposed them, with measures of acceptance, rewrites and time to resolution.
- **A ledger of its own**, in memory or in SQL, behind the `sql`, `sqlite` and `postgres` extras.

## Documentation

relayr's documentation is its section of lattice's site, at **<https://lattice.alexnodeland.com/relayr/>**, built from [`docs/relayr/`](https://github.com/alexnodeland/lattice/tree/main/docs/relayr). Its guides and architecture come with the phases that build what they describe.

- [Architecture decision records](https://lattice.alexnodeland.com/relayr/adr/): why each part will be the way it is.
- [RFCs](https://lattice.alexnodeland.com/relayr/rfcs/): the v0.1 plan, its phases and what each waits on.
- [The combined system](https://lattice.alexnodeland.com/stackr/rfcs/0002-the-combined-system/), stackr's RFC-0002: the design relayr builds.
- [Brand](https://lattice.alexnodeland.com/relayr/assets/brand/): the mark and its colours.

## Contributing

See [CONTRIBUTING.md](https://github.com/alexnodeland/lattice/blob/main/CONTRIBUTING.md) for setup, the trunk-based workflow, and the RFC and ADR process.

## License

[MIT](https://github.com/alexnodeland/lattice/blob/main/packages/relayr/LICENSE)
