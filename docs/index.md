---
title: lattice
description: The family's packages, for applications in which people and agents work together, and the stack they run on.
---

# lattice

The family's packages, in one repository: libraries for applications in which people and agents work together, and the stack they run on. Each package has its own section.

| Package | What it is |
|---|---|
| [artifactr](artifactr/index.md) | Chat applications where people and agents collaborate through shared, versioned artifacts |
| [reflexr](reflexr/index.md) | Rules over event streams that run LLM workflows: pydantic-ai agents, pydantic-graph graphs and functions |
| [evalr](evalr/index.md) | Typed evaluation of agent systems: judges that give typed verdicts, trained on people's feedback and measured against it |
| [relayr](relayr/adr/README.md) | The bridge between artifactr and reflexr: events from chats and artifacts become events for rules, and runs act back in the chat |
| [stackr](stackr/index.md) | The infrastructure the libraries run on, and an application template |

Two more are planned: grantr, identity and access for artifactr and reflexr, and portalr, the portal into the system.

The source is [alexnodeland/lattice](https://github.com/alexnodeland/lattice). To work on it, see [Contributing](project/contributing.md).
