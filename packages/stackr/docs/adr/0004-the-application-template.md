# ADR-0004: The application template

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

A new application on the libraries has to wire several things before it does anything useful:

- authentication to actors
- storage to Supabase
- telemetry to the Collector
- agents to the gateway
- feedback types and evals

Doing that by hand is where applications diverge and where mistakes hide.

## Decision

- stackr includes a **Copier template** that generates an application using artifactr, reflexr or both, wired to the stack, with a dev container, CI and the family's quality gates.
- **`copier update`** brings later template improvements into generated applications.
- The template is tested in CI by generating an application and running its checks and the stack's smoke test.

## Consequences

- Easier: a new application starts correct, and improves with the template.
- Harder: the template must track the libraries' APIs; CI generating an application catches drift.

## Action items

1. [ ] Implement RFC-0001 phase 5.
