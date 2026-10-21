# ADR-0017: A person's upload, told by its bytes, read by the app before it is committed, and held to quotas

**Status:** Accepted
**Date:** 2026-10-21
**Deciders:** Alex Nodeland
**Amends:** [ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md), whose routes made no new file

## Context

Files entered a workspace only through `NativeFiles.upload`, in an application's code: no route created a native file, and portalr had no control for it, so a person could check a file out and in but never add one. `upload` took the client's media type on trust and the name as given, and the routes relayed an `AppFailed`'s message, whose `crashed` text ends with what the CLI printed and which a hostile file can shape ([ADR-0013](0013-the-worker-runs-each-call-under-limits-behind-a-token.md)). Nothing bounded what a workspace or a tenant stored, how fast one person sent files, or how many of a tenant's files the worker, which runs one job at a time, was asked to read at once.

## Decision

- **`POST /workspaces/{w}/files?kind=&name=`, the file's bytes as the whole body**, as a check-in's are: streamed into the blob store, never `multipart/form-data`, which would be parsed into memory or a temporary file before any limit. The route answers `201` with `Uploaded` (`applied` and its version, or `proposed`), or `200` with `unchanged`. `GET /workspaces/{w}/uploads` says whether the person may upload, the limit, and each native type's extensions and whether its app is on, for a file picker and for saying why the control is off.
- **Before a byte is read**, the workspace is opened as the person (`resolve_actor`, then `authorize`'s `artifactr:open`); `authorize` is asked **`artifactr:create_native_file`**, a new action in artifactr's catalog that grantr gives editors, as it does `artifactr:create_artifact`, which the commit asks too; `kind` must be a registered native type; a `Content-Length` past the limit is `413`; and the person's pace is counted. The app's switch is asked by `upload`, before the stream is read.
- **The size is held as the body streams**, whatever `Content-Length` said: the store's spool refuses past its own limit, so a body that lies is still `413`. The store's most, 100 MiB, is below the worker's, 256 MiB (`Limits.files`), so the store refuses a file before the worker would.
- **The format is the bytes', never the client's.** `Content-Type` is not read; `kind` names the native type, and the first 4 KiB are matched against each of its formats' signatures (`FORMATS`: a zip's, `%PDF-`, `8BPS`, `AC10xx`, a DXF's first group, an `<svg` element). A signature never opens a zip: every format packaged in one matches any zip, and the app tells them apart. Bytes of none of the type's formats, or none at all, are `AppFailed("refused")` before they are stored. The app's inspection, in the worker, then reads the file before anything is committed; a format it reads as another, or a failure, commits nothing. An application with a native type of its own gives `NativeFiles` its format's signature and extension.
- **The name is kept safe**: the last part of any path, NFC, every control character and every one a file system refuses replaced by `_`, at most 200 characters, and the format's extension, replacing one of another format's.
- **An upload sent again makes nothing twice.** The client may give the artifact's id (`artifact_id`, `[A-Za-z0-9_-]{1,128}`): a native file with that id whose content is the same bytes is `unchanged`; another is `409`. Bytes are deduplicated within an artifact, by the store's key, and never across artifacts or tenants, which would tell an uploader that someone else has a file ([ADR-0002](0002-blobs-in-a-port-of-the-package.md)).
- **A client is told how the app failed in the route's words, never the app's**: `refused`, `too_large`, `timeout` and `crashed` each have a fixed sentence, on every route, check-ins too; the app's message goes to the operator's log, `artifactr.files`, at warning.
- **Quotas are the blob store's**: `workspace_quota` and `tenant_quota`, each a `Quota` of bytes and files. A file is an artifact with bytes in the store, so an upload counts from its put, uncommitted ones too, until collection deletes what nothing names: a person can't send junk past a quota by having it refused. `SqlBlobs` counts in the transaction that inserts, after locking the tenant's row of `artifactr_files_tenants` (migration 0002, under row-level security), so puts at once can't pass a quota together; only new bytes are counted, and only a new artifact is a new file. A put past one is `OverQuota`, `413` with `over_quota` and which quota.
- **Pace and readings are this process's**: `files_router(uploads_per_minute=20)` holds each participant to a sliding minute (`429`, `rate_limited`, `Retry-After`); `NativeFiles(readings=n)` lets each tenant have `n` files read by the app at once, uploads and check-ins, and refuses another at once with `Busy` (`429`, `busy`, `Retry-After: 5`), so one person's uploads never queue everyone's behind the worker. Each replica keeps its own counts.
- **Every upload is recorded** on the `artifactr.files.uploads` logger, whatever its outcome: actor, tenant, workspace, kind, the digest and size of what was read (no digest unless all of it was), the outcome, and a refusal's status. A committed upload is also the log's `artifact_created`, with the manifest.
- **The agent gets no tool to upload.** A model never sends a file's bytes, in base64 or otherwise: its tools edit a file by the app's commands ([ADR-0006](0006-the-agents-tools-behind-each-apps-switch.md)). A tool that takes a blob a person already uploaded adds nothing in v0.2, since the person's upload is already the file; it is reconsidered if a person's upload ever stops short of an artifact.

## Options considered

### Option A: The route, the store and `NativeFiles`, each holding what it already knows (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a route, a format table, a quota in two stores, a pace, a count |
| Safety | Each limit where it is enforced cheapest: the action and length before the body, the size as it streams, the format before a put, the app before a commit, the quota in the insert's transaction |
| Fit | `upload` already put, inspected, then committed; the route is a check-in's |

**Pros:** every surface that calls `upload` gets the format, the name and the retry; the quota is exact on SQL.
**Cons:** the pace and the readings are per process.

### Option B: `multipart/form-data`

**Cons:** Starlette parses the form, spooling the file to memory or disk, before the route sees it, so no limit holds as it streams; a browser sends a `File` as a body as easily.

### Option C: Quotas in artifactr's storage, counted from committed manifests

**Cons:** the count would be a second transaction beside the put's, and uploads refused after their put, or never committed, would hold bytes no quota counts.

### Option D: A per-tenant queue in front of the worker

**Cons:** a queue that waits holds a request open behind another tenant's slow file; refusing at once tells the client to wait, which it does better.

## Trade-off analysis

Option A puts each check where the fact it needs is already in hand, and keeps the HTTP layer thin: the route resolves, gates and maps refusals, and `NativeFiles` and the stores decide. Its weakness, counts per process, is the same as every replica's own memory, and the store's quota, the one that must be exact, is not.

## Consequences

- Easier: a person adds a file in portalr, by picking or dropping it, and an application's code that calls `upload` without a media type gets the same checks.
- Easier: a retry after a connection drops is safe, since the client chose the id.
- Harder: an application with its own native type must give `NativeFiles` its format, or its files can't be uploaded by people (the type's `extensions` are empty, and portalr offers none).
- Harder: pace and readings multiply with replicas; a deployment with several sets them per replica, or puts its own limit in front.
- Harder: a quota counts uncommitted bytes until collection, a day by default, so a workspace near its quota frees space only after `collect` runs.
- Revisit: a quota per tenant's plan, read from a port, if deployments want them to differ.

## Action items

1. [x] `files_router`: `POST /workspaces/{w}/files`, `GET /workspaces/{w}/uploads`, the fixed failure sentences, the pace and the record.
2. [x] `NativeFiles.upload`: the format by its bytes, the name, the retry, `readings`; `FORMATS`.
3. [x] `Quota` on `InMemoryBlobs` and `SqlBlobs`, migration 0002.
4. [x] `artifactr:create_native_file` in artifactr's catalog and grantr's editor; the matrices regenerated.
5. [x] portalr: the control on the artifacts page and in the thread composer.
6. [ ] stackr: the quotas, the pace and the readings in the generated application's settings (after stackr's native files land).
