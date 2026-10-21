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
- **The size and the pace are held as the body streams**, whatever `Content-Length` said: the store's limit (the router's may only be smaller, and is the store's by default), a pause of 30 seconds between chunks, and 32 KiB a second on average after it (`Body`), past which it is `408`, `too_slow`. Each upload is held in memory, so the router takes at most `uploads_at_once`, 8, at once from every tenant, refusing another with `429`, `busy`. A server closes the connection after refusing a body it didn't read; put a reverse proxy's own body limit and timeouts in front as well. The store's most, 100 MiB, is below the worker's, 256 MiB (`Limits.files`).
- **The format is the bytes', never the client's.** `Content-Type` is not read; `kind` names the native type, and the first 4 KiB are matched against each of its formats' signatures (`FORMATS`). A signature never opens a zip, so a format packaged in one is not `told` by its bytes: the app must then name the format it read, or the upload is refused. Bytes of none of the type's formats are `AppFailed("refused")`. The app reads the file **before anything is stored**: only then are the file, its words and its review put, together, all or none (`Blobs.put_all`), so a refused upload holds nothing against a quota. A format the app names other than the kind's is refused in the route's words, never with the name the app gave, which is the worker's text.
- **The name is kept safe**: the last part of any path, NFC, every control character and every one a file system refuses replaced by `_`, at most 200 characters, and the format's extension, replacing one of another format's.
- **An upload sent again makes nothing twice.** The client may give the artifact's id (`artifact_id`, `[A-Za-z0-9_-]{1,128}`): it is looked up before the app is asked, and a native file with that id whose content is the same bytes is `unchanged`; another, or one the person can't see, is `409`, `already exists`, alike. Bytes are deduplicated within an artifact, by the store's key, and never across artifacts or tenants, which would tell an uploader that someone else has a file ([ADR-0002](0002-blobs-in-a-port-of-the-package.md)): the same bytes under a new id are stored, and counted, again.
- **A client is told how the app failed in the route's words, never the app's**: `refused`, `too_large`, `timeout` and `crashed` each have a fixed sentence, on every route, check-ins too; the app's message goes to the operator's log, `artifactr.files`, at warning.
- **Quotas are the blob store's**, and off unless given: `workspace_quota` and `tenant_quota`, each a `Quota` of bytes and files. A file is an artifact with bytes in the store. `SqlBlobs` counts in the transaction that inserts, after locking the tenant's row of `artifactr_files_tenants` (migration 0002, under row-level security), which holds under PostgreSQL's default `READ COMMITTED` (a `REPEATABLE READ` snapshot would predate the lock) and SQLite's `BEGIN IMMEDIATE`. The count is a sum over the tenant's rows under that lock, so a tenant's puts are serialised; a running counter is the step if that shows. A put past one is `OverQuota`, `413` with `over_quota` and which quota. Nothing in lattice sets them yet: stackr's generated application will.
- **Pace and readings are this process's**: `files_router(uploads_per_minute=20)` holds each of a tenant's participants to a sliding minute (`429`, `rate_limited`, `Retry-After`), letting go of those idle a minute; `NativeFiles(readings=2)` lets each tenant have two files read by the app at once, uploads and check-ins, and refuses another at once with `Busy` (`429`, `busy`, `Retry-After: 5`). Each replica keeps its own counts.
- **Every upload is recorded**, as a line on the `artifactr.files.uploads` logger, its fields in `extra` (the application's log handler keeps it; it is not the event log): actor, tenant, workspace, kind (held to a pattern), the digest and size of what was read (no digest unless all of it was), the outcome (`error` for one that ended otherwise than in an answer), and a refusal's status, a sign-in refused too. A committed upload is also the log's `artifact_created`, with the manifest. The app's failure is logged as a `repr`, so its text can't forge a line.
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

**Cons:** the count would be a second transaction beside the put's.

### Option D: A per-tenant queue in front of the worker

**Cons:** a queue that waits holds a request open behind another tenant's slow file; refusing at once tells the client to wait, which it does better.

## Trade-off analysis

Option A puts each check where the fact it needs is already in hand, and keeps the HTTP layer thin: the route resolves, gates and maps refusals, and `NativeFiles` and the stores decide. Its weakness, counts per process, is the same as every replica's own memory, and the store's quota, the one that must be exact, is not.

## Consequences

- Easier: a person adds a file in portalr, by picking or dropping it, and an application's code that calls `upload` without a media type gets the same checks.
- Easier: a retry after a connection drops is safe, since the client chose the id.
- Harder: an application with its own native type must give `NativeFiles` its format, or its files can't be uploaded by people (the type's `extensions` are empty, and portalr offers none).
- Harder: pace and readings multiply with replicas; a deployment with several sets them per replica, or puts its own limit in front.
- Harder: an upload refused at its commit, such as one with an id the person can't see, leaves its bytes counted until collection, a day by default.
- Revisit: a quota per tenant's plan, read from a port, if deployments want them to differ.

## Action items

1. [x] `files_router`: `POST /workspaces/{w}/files`, `GET /workspaces/{w}/uploads`, the fixed failure sentences, the pace and the record.
2. [x] `NativeFiles.upload`: the format by its bytes, the name, the retry, `readings`; `FORMATS`.
3. [x] `Quota` on `InMemoryBlobs` and `SqlBlobs`, migration 0002.
4. [x] `artifactr:create_native_file` in artifactr's catalog and grantr's editor; the matrices regenerated.
5. [x] portalr: the control on the artifacts page and in the thread composer.
6. [ ] stackr: the quotas, the pace and the readings in the generated application's settings (after stackr's native files land).
