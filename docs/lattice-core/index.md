---
title: lattice-core
description: What lattice's libraries share and must keep identical, which each depends on and re-exports.
---

# lattice-core

What lattice's libraries share and must keep identical. artifactr, reflexr, grantr and relayr never import one another ([reflexr ADR-0003](../reflexr/adr/0003-independent-sibling-of-artifactr.md)), but some of their infrastructure is the same code, and must stay the same. It lives here once, and each library depends on it ([lattice ADR-0018](../adr/0018-lattice-core-what-the-libraries-share.md)).

!!! note "Not for applications"

    An application imports from the library it uses: each re-exports what it makes public from here, so its API is unchanged. lattice-core's own API may change with any library's needs.

## What it holds

| Module | What | Shared by |
|---|---|---|
| [`lattice_core.schema`](reference.md#lattice_coreschema) | `tag_required`, which makes a union member's tag required in its JSON Schema | artifactr, reflexr |
| [`lattice_core.text`](reference.md#lattice_coretext) | `holds_nul`, which finds a NUL character, which PostgreSQL's text can't store, anywhere in a value | artifactr, reflexr |

The libraries' SQL helpers and their OpenTelemetry setup move here next, as ADR-0018 plans.

## What doesn't belong here

Nothing about a library's domain: no events, commands, storage or rules. Only code that is the same in two or more libraries, and must stay the same; code that only looks alike stays where it is.

## Installing it

You don't install it yourself: each library requires it. Its distribution is `lattice-core-ai`, since the name `lattice-core` on PyPI is an unrelated project, and it is imported as `lattice_core`. Until the packages are on PyPI, uv installs it from the same commit of lattice as the library that needs it.
