---
title: Native files
description: Native files as artifactr artifacts, a manifest over the file's bytes, edits by the file's own app, and one writer at a time.
---

# Native files

Native files as [artifactr](../index.md) artifacts, in artifactr's `files` extra, imported as `artifactr.files`. A Word document, and later a deck, a spreadsheet or a drawing, is an artifact whose data is a small manifest naming the file's bytes, by their SHA-256, in a blob store. The file is the source of truth, and nothing parses it into fields.

!!! note "Phases 1 and 2 of lattice RFC-0003, unreleased"

    Built and tested: the types, the revision that tests its base, the blob store in memory and in SQL, check-outs, the app port with a fake app, and native files in a workspace: uploads, check-out and check-in, agents' edits and collection ([lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#phases), phase 1); WordCraft headless, its adapter, pinned by checksum, with a fidelity report every night (phase 2); the agent's tools, behind each app's switch in the workspace (phase 3); and check-out and check-in over HTTP, with WordCraft's browser build served as released on an origin of its own (phase 4's server side). artifactr's lease on an artifact, which it holds, is [artifactr ADR-0071](../adr/0071-a-lease-on-an-artifact.md).

    Not built yet: the sandboxed worker (phase 3), portalr's renderer, previews and check-out screens (phase 4), and the streamed session (phase 5). It is in no release yet; it will ship in `artifactr-ai`, installed as `artifactr-ai[files]`.

## Why: work arrives as files

The documents people and agents share are often a contract in `.docx`, a deck in `.pptx` or a model in `.xlsx`, and artifactr's types hold JSON and Markdown. Converting a file to Markdown loses its styles, tables, comments and tracked changes; keeping it outside artifactr loses revisions, proposals, attribution and the log. An app that reads and writes the format natively, and exposes its edits as commands, lets an agent change the real file.

## What it does

- **A manifest over the bytes.** `WordDocument` names its content, its text and its review (comments and tracked changes) as blobs, with a fingerprint, an outline and its provenance. Bytes never enter artifactr's log, its events or its replays ([artifactr ADR-0072](../adr/0072-native-files-are-manifests-over-json-patch.md)).
- **Revisions that test their base.** Every revision is JSON Patch whose first operation tests `/content/sha256`, so accepting a proposal made against an old version fails with `PatchFailed` rather than replacing what came after.
- **One writer at a time.** A person's check-out holds a lease on the artifact for eight hours; an agent's edit holds one for the app's call and the commit. Someone else is refused with `ArtifactBusy`, which says who has the file ([ADR-0003](adr/0003-check-outs-and-agents-edits-under-one-lease.md)).
- **A blob store of its own,** keyed by tenant, workspace, artifact and digest, in memory or in SQL, with row-level security on PostgreSQL ([ADR-0002](adr/0002-blobs-in-a-port-of-the-package.md)).
- **An app port,** stateless calls of bytes in and bytes out, and a fake app that every pull request's tests run with ([ADR-0004](adr/0004-an-app-is-a-port-of-stateless-calls.md)).
- **WordCraft, headless,** for `.docx`: its CLI's MCP server, spawned for every call and confined to the call's own directory, at a release pinned by checksum, whose fidelity Nightly reports feature by feature ([ADR-0005](adr/0005-wordcraft-headless-pinned-by-checksum.md)).
- **An extra of artifactr,** `artifactr-ai[files]`, which depends inward on artifactr's public API only, and which the shared Integrations switch turns on per workspace, one key an app ([lattice ADR-0026](../../adr/0026-a-distribution-needs-a-reason-integrations-are-extras.md)). It was planned as a separate distribution, `artifactr-files-ai` ([ADR-0001](adr/0001-a-separate-distribution.md), superseded), and was folded in before its first release.

Start with the [guide](guides/native-files.md); [the architecture](architecture.md) says how it works.
