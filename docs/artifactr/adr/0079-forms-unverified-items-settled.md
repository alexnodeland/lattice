# ADR-0079: Forms' unverified items, settled

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) listed what it had not verified, each to be settled by a test and recorded in an ADR. Two are phase 1's.

## Decision

- **A 32 KB schema survives `CallDeferred`, `run_paused`, storage and resume unchanged.** `tests/ui/test_agent.py` asks a form whose title and schema are within 100 bytes of `MAX_SCHEMA_BYTES` as stored, with non-ASCII text, through artifactr's `Runner` on a scripted model, on in-memory storage, SQLite and PostgreSQL: the paused run's request, the `run_paused` event read back from the log, and the call in the resumed turn's history each hold the arguments exactly as the model made them. Settled: pydantic-ai keeps them, and artifactr stores them as JSON.
- **Reserving `ui:` refuses a client's publish.** relayr's `tests/ui/test_ui.py` publishes a `FormSubmitted` as a person's client into a reflexr workspace with `UI_PUBLISHERS`, which is refused (`Forbidden`, "reserved to source:artifactr"), and as relayr's `SOURCE`, which is published; and runs relayr's follower end to end, where an `ask_form` answer and a submission each fire a rule on `ui:form_submitted` once, a submission to an app `ui:app_submitted` once, and a retried submit nothing more. Settled.

## Consequences

- The browser's behaviour in a sandboxed frame and `mcp.server.apps` remain the RFC's, for phases 2 and 3.
