---
title: lattice-core
description: What lattice's packages share and must keep identical, which each depends on and re-exports.
---

# lattice-core

What lattice's packages share and must keep identical. artifactr, reflexr and grantr import none of one another, and relayr bridges artifactr and reflexr ([reflexr ADR-0003](../reflexr/adr/0003-independent-sibling-of-artifactr.md)). Where two of them would otherwise copy the same code, they depend on lattice-core, which imports no lattice package ([lattice ADR-0018](../adr/0018-lattice-core-what-the-libraries-share.md)).

!!! note "Not for applications"

    An application imports from the package it uses: each re-exports what it makes public from here, so its API is unchanged.

## What it holds

| Module | What | Shared by |
|---|---|---|
| [`lattice_core.schema`](reference.md#lattice_coreschema) | `tag_required`, which makes a union member's tag required in its JSON Schema | artifactr, reflexr |
| [`lattice_core.text`](reference.md#lattice_coretext) | `holds_nul`, which finds a NUL character, which PostgreSQL's text can't store, anywhere in a value | artifactr, reflexr |

The SQL helpers, the OpenTelemetry setup and the REST routers' refusal schema move here next, as ADR-0018 plans.

## What belongs here

Only infrastructure that is the same in two or more packages, word for word but for their names, and must stay the same. Code that only looks alike stays where it is, and nothing about a package's domain belongs here. lattice-core changes only by addition and deprecation, and each package requires a lower bound of it.

## Installing it

You don't install it yourself: the packages that need it require it. Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`. Until the packages are on PyPI, uv installs it from the same commit of lattice as the package that needs it.
