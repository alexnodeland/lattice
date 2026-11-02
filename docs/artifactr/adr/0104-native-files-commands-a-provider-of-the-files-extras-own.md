# ADR-0104: Native files' commands, a provider of the files extra's own

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0014](../../rfcs/0014-portr-the-command-catalog-and-the-mcp-acp-gateway.md)'s Tracking item "artifactr, grantr, reflexr, relayr, portalr: their catalogs, providers, ..." for artifactr's last two commands (#916); the follow-up [ADR-0103](0103-artifactrs-catalog-bound-to-its-workspaces-and-runner-every-command-a-client-may-call.md) leaves

## Context

ADR-0103's catalog provider serves every exposed command of artifactr's catalog except `artifactr.list_files` and `artifactr.read_file`. Reading a native file's words needs the files extra's `NativeFiles`, which `artifactr.capabilities` may not import: an application without the extra has no native files, and the provider must import without it. RFC-0014's core toolset lists both commands.

## Decision

- **`artifactr.files.capabilities.NativeFilesProvider(workspaces, files, *, actor=actor_for)`**, in the files extra, is lattice-core's `Provider` for those two commands. It offers them as the catalog declares them.
- **An application binds it beside the catalog provider** when it has native files. The two share no name, so one registry holds both.
- **It opens the call's workspace as `actor_for`'s actor,** as the catalog provider does, so the workspace's `authorize` and hidden artifacts hold for each read. A call that names no workspace is refused.
- **`artifactr.list_files`** answers one JSON line per native file: its id, version, kind, name, media type, size and pages.
- **`artifactr.read_file`** answers a page of the words the file's app read from it, 8,000 characters a page, as kept: the files router's text does the same, and neither asks the app again. A page past the last says how many there are.

## Options considered

### Option A: A provider in the files extra (chosen)

**Pros:** `artifactr.capabilities` keeps importing nothing of the extra, and an application with native files binds one more provider.
**Cons:** two providers serve artifactr's catalog, and an application without the extra never offers the two commands.

### Option B: The catalog provider takes an optional reader

**Cons:** a port in `artifactr.capabilities` for one extra's two reads. The extra would still build its adapter, and the catalog provider would offer commands it can't carry out when no reader is given.

## Consequences

- Easier: portr offers a client every command of artifactr's core toolset, native files' among them.
- To revisit: RFC-0014's `artifactr_search`, which artifactr has no read for yet.
