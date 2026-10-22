# Uploads and quotas, for operators

A person adds a native file by uploading it: portalr's "Upload" in a workspace, or any client of `files_router`'s route. This page is what an operator sets and what a refusal means. [Native files](native-files.md) covers the library underneath, and [ADR-0017](../adr/0017-a-persons-upload-told-by-its-bytes-read-before-it-is-committed.md) records why.

## The route

```
POST /artifactr/v1/workspaces/{workspace_id}/files?kind=word_document&name=terms.docx
```

The body is the file's bytes, streamed. The client's `Content-Type` is never read: the file's format is the one of the kind's formats its first bytes are. The app reads the file in its worker before anything is stored or committed, so a file it can't read holds nothing against a quota. An `artifact_id` makes a retry safe: an upload whose file with that id already has these bytes answers `200`, `unchanged`, and commits nothing.

`GET .../workspaces/{workspace_id}/uploads` tells a client what it may upload there: whether the person may, the largest file, and each kind an app reads, with its extensions, its own largest file, and whether its app is on in the workspace.

## What an operator sets

In a generated application's `.env` (stackr's template), each read when the application starts:

| Setting | Default | What it holds back |
|---|---|---|
| `FILES_UPLOADS_PER_MINUTE` | 20 | Uploads each person may start in a minute, in this process |
| `FILES_UPLOADS_AT_ONCE` | 8 | Uploads and check-ins this process takes at once, from every tenant: each is held in memory |
| `FILES_UPLOADS_PER_TENANT` | half of `AT_ONCE` | How many of those places one tenant's people may hold |
| `FILES_UPLOADS_EACH` | 2 | How many of those places one person may hold |
| `FILES_READINGS` | 2 | How many of a tenant's files its apps read at once |
| `FILES_WORKSPACE_QUOTA` | none | The most a workspace's files may hold: `<bytes>` or `<bytes>,<files>`, such as `2147483648,1000` |
| `FILES_TENANT_QUOTA` | none | The same, for each tenant |

Each worker's own limits are `FILES_WORKER_MEMORY`, `FILES_WORKER_CPUS`, `FILES_WORKER_TMPFS` and `FILES_WORKER_LIMITS` ([stackr ADR-0043](../../../stackr/adr/0043-native-files-in-the-template.md)). The largest file is the blob store's limit, and a format's own limit if it is smaller.

The counts are each process's own: an application run as several replicas allows each replica its own.

A body must keep arriving: after a pause of 30 seconds, or below 32 KiB a second on average, the upload is refused.

## What a refusal means

| Status | `detail.type` | What happened | What to do |
|---|---|---|---|
| 413 | none, or `over_quota` | The file is larger than the limit, or would take the workspace or the tenant past its quota (`quota` names which) | A smaller file, or a larger quota |
| 429 | `busy` | The process's, the tenant's or the person's places are all taken, or the tenant's files are all being read. `Retry-After` says when to try again | Wait; portalr does |
| 429 | `rate_limited` | The person is past their uploads a minute | Wait the `Retry-After` |
| 408 | `too_slow` | The body stopped arriving | Send it again |
| 422 | `app_failed`, `refused` | The bytes are no file of the kind's, or the app can't read them | Check the file |
| 409 | `invalid_state` | A file with this `artifact_id` already exists with other bytes | A new id |
| 409 | `not_enabled` | The kind's app is off in the workspace | Switch its integration on |
| 503 | `app_failed` | The app's worker didn't finish: it timed out or crashed | Try again; read the worker's logs |

An upload never says what a worker printed: a hostile file can shape that, so it goes to the application's log alone.

## Quotas

A quota counts bytes and files, artifacts with bytes in the store. It is checked as new bytes are put, in the same transaction, under a lock on the tenant's row, so two uploads at once never pass it together. Every version's bytes count while a revision or a pending proposal names them. `NativeFiles.collect` deletes bytes that nothing names, once they are a day old, and so gives them back.
