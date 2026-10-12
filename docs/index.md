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
| [grantr](grantr/index.md) | Identity and access for artifactr and reflexr: tenants, members, groups, roles and service principals, checked before every command and read |
| [stackr](stackr/index.md) | The infrastructure the libraries run on, and an application template |
| [portalr](portalr/index.md) | The portal into an application: an app UI to chat with its agents and see their work, and an admin UI to run it. In progress: its router and readers are built |

grantr's core, storage and admin API are built, and [its plan](grantr/rfcs/0001-v0.1-implementation-plan.md) wires it into the libraries and the template. portalr's router and readers are built, and [its plan](portalr/rfcs/0001-v0.1-implementation-plan.md) builds the UIs on them.

lattice's mark is one cell of the lattice that every mark in the family is drawn on. Its [brand page](assets/brand/README.md) has the mark, the colours and the family's brand system, and [ADR-0001](adr/0001-lattices-brand.md) records why.

How the family fits together, in one repository, is in [Architecture](architecture.md), and the decisions about the family as a whole are in [its ADRs](adr/README.md). The source is [alexnodeland/lattice](https://github.com/alexnodeland/lattice). To work on it, see [Contributing](project/contributing.md).
