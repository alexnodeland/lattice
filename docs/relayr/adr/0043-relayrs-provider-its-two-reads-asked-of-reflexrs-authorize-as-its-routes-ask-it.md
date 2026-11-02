# ADR-0043: relayr's provider: its two reads, asked of reflexr's `authorize` as its routes ask it

**Status:** Accepted
**Date:** 2026-11-02
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Tracking item "artifactr, grantr, reflexr, relayr, portalr: their catalogs, providers, ..." for relayr (#916); beside [ADR-0042](0042-relayrs-commands-the-tracker-connectors-reads-gated-by-reflexrs-actions.md)

## Context

ADR-0042 declares relayr's two commands, `relayr.list_filed_items` and `relayr.tracker_status`, but nothing served them except the portal's REST reads, whose logic lived in the router's closures in the `fastapi` extra. portr reaches commands only through lattice-core's registry (lattice ADR-0043), so relayr needs a provider, and the provider can't import FastAPI.

## Decision

- **The reads move out of the router.** `relayr.trackers.filed_in(trackers, workspace)` and `following_in(trackers, workspace)`, with their models (`Filed`, `FiledItem`, `Following`, `Reading`, `Writes`), now live in `relayr.trackers`, which imports no FastAPI. The router calls them and still exports the models from `relayr.fastapi`, so nothing changes for its callers.
- **`relayr.capabilities.RelayrProvider(trackers, workspaces, *, actor=reflexr's actor_for)`** is lattice-core's `Provider` and `Commands` for the two reads, in a layer of its own.
- **It opens the call's reflexr workspace as the actor reflexr's provider would** (the client acting for the person), and asks its `authorize` for the reflexr action the command's gate names, as relayr's routes do. It answers what the routes answer, as JSON.
- **Neither command takes an argument**, and a call that names no workspace is refused.

## Options considered

### Option A: Move the reads into `relayr.trackers`, and a provider of their own (chosen)

**Pros:** the routes and the provider answer the same, from one function each, and the provider needs no FastAPI.
**Cons:** the reads' models move module, re-exported where they were.

### Option B: The provider calls the router in-process

**Cons:** the `fastapi` extra would become the provider's dependency, and each call would go through a request it doesn't need.

## Consequences

- Easier: portr offers a client relayr's reads in the `automations` toolset.
- To revisit: none of relayr's own; rules drafted in a chat stay artifactr's and reflexr's commands.
