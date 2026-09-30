---
title: lattice
description: The family's packages, for applications in which people and agents work together, and the stack they run on.
---

<div class="lattice-hero" markdown>

<h1 class="lattice-visually-hidden">lattice</h1>

![lattice](assets/brand/lockup-light.svg#gh-light-mode-only)
![lattice](assets/brand/lockup-dark.svg#gh-dark-mode-only)

The family's packages, in one repository: libraries for applications in which people and agents work together, and the stack they run on. Each package has its own section.

</div>

![The marks of artifactr, reflexr, evalr, relayr, stackr and lattice, over their names](assets/brand/family-light.svg#gh-light-mode-only)
![The marks of artifactr, reflexr, evalr, relayr, stackr and lattice, over their names](assets/brand/family-dark.svg#gh-dark-mode-only)

| Package | What it is |
|---|---|
| [artifactr](artifactr/index.md) | Chat applications where people and agents collaborate through shared, versioned artifacts |
| [reflexr](reflexr/index.md) | Rules over event streams that run LLM workflows: pydantic-ai agents, pydantic-graph graphs and functions |
| [evalr](evalr/index.md) | Typed evaluation of agent systems: judges that give typed verdicts, trained on people's feedback and measured against it |
| [relayr](relayr/index.md) | The bridge between artifactr and reflexr: events from chats and artifacts become events for rules, and runs act back in the chat |
| [stackr](stackr/index.md) | The infrastructure the libraries run on, and an application template |

Two more are planned: grantr, identity and access for artifactr and reflexr, and portalr, the portal into the system.

lattice's mark is one cell of the lattice that every mark in the family is drawn on. Its [brand page](assets/brand/README.md) has the mark, the colours and the family's brand system, and [ADR-0001](adr/0001-lattices-brand.md) records why.

How the family fits together, in one repository, is in [Architecture](architecture.md), and the decisions about the family as a whole are in [its ADRs](adr/README.md). The source is [alexnodeland/lattice](https://github.com/alexnodeland/lattice). To work on it, see [Contributing](project/contributing.md).
