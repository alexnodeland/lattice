---
title: lattice
description: Libraries for applications in which people and agents work together, and the stack they run on.
---

<div class="lattice-hero" markdown>

<h1 class="lattice-visually-hidden">lattice</h1>

![lattice](assets/brand/lockup-light.svg#gh-light-mode-only)
![lattice](assets/brand/lockup-dark.svg#gh-dark-mode-only)

Libraries for applications in which people and agents work together, and the stack they run on, in one repository. Each package has its own section.

</div>

![The marks of artifactr, reflexr, evalr, relayr, stackr, portalr, grantr and lattice, over their names](assets/brand/family-light.svg#gh-light-mode-only)
![The marks of artifactr, reflexr, evalr, relayr, stackr, portalr, grantr and lattice, over their names](assets/brand/family-dark.svg#gh-dark-mode-only)

| Package | What it is |
|---|---|
| [artifactr](artifactr/index.md) | Chat applications where people and agents collaborate through shared, versioned artifacts |
| [reflexr](reflexr/index.md) | Rules over event streams that run LLM workflows: pydantic-ai agents, pydantic-graph graphs and functions |
| [evalr](evalr/index.md) | Typed evaluation of agent systems: judges that give typed verdicts, trained on people's feedback and measured against it |
| [relayr](relayr/index.md) | The bridge between artifactr and reflexr: events from chats and artifacts become events for rules, and runs act back in the chat |
| [grantr](grantr/index.md) | Identity and access for artifactr and reflexr: tenants, members, groups, roles and service principals, checked before every command and read |
| [stackr](stackr/index.md) | The infrastructure the libraries run on, and an application template |
| [portalr](portalr/index.md) | The portal into an application: an app UI to chat with its agents and see their artifacts, proposals and runs, and an admin UI to run it |
| [lattice-core](lattice-core/index.md) | What the packages share and must keep identical: infrastructure each depends on and re-exports, never imported by an application |

Every package is released: the libraries on PyPI, and stackr's images on GHCR. stackr's [hosting recipes](stackr/rfcs/0004-hosting-recipes.md) are being built.

lattice's mark is one cell of the lattice that every package's mark is drawn on. Its [brand page](assets/brand/README.md) has the mark, the colours and the brand system every package shares, and [ADR-0001](adr/0001-lattices-brand.md) records why.

How the packages fit together, in one repository, is in [Architecture](architecture.md), and the decisions about lattice as a whole are in [its ADRs](adr/README.md). The source is [alexnodeland/lattice](https://github.com/alexnodeland/lattice). To work on it, see [Contributing](project/contributing.md).
