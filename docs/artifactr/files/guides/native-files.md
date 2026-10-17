# Native files

A native file is an artifact whose data is a manifest over the file's bytes. This guide wires the package into an application and walks through what people and agents do with a file. Everything here runs with the fake app; the WordCraft adapter comes in a later phase of [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md).

## The types

`WordDocument` is registered as `word_document` and holds `.docx` files (`DOCX`). Its manifest names three blobs, its content, its text and its review, and holds a fingerprint, an outline of up to 4,000 characters, its page count if known and its provenance:

```python
from artifactr_files import WordDocument

WordDocument.formats  # frozenset({DOCX})
WordDocument.write_policy  # "propose": an agent's edit is a proposal
```

A type for another format subclasses `NativeFile` and names its media types in `formats`; a manifest whose content isn't one of them doesn't validate. What the agent sees by default is the file's name, its pages if known and its outline: `render_for_agent` does no IO, so it shows what the app read from the file when the revision was made. The fingerprint is the digest of the content with what each save stamps, such as the time, left out, so a save that changes nothing else makes no revision.

## Wiring it in

`NativeFiles` takes a blob store, a check-out store and an app. Every method takes the `Workspace` to act in, so `authorize` and the hiding of restricted artifacts apply as for any read or command:

```python
from artifactr_files import FakeApp, InMemoryBlobs, InMemoryCheckouts, NativeFiles

files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
```

In production, both stores are SQL, behind the `postgres` or `sqlite` extra. Migrate as the tables' owner; with row-level security, grant a role that owns nothing and give the stores its engine, as artifactr's storage has it:

```python
from artifactr_files.sql import SqlBlobs, SqlCheckouts, migrate

await migrate(owner, application_role="app")
files = NativeFiles(
    SqlBlobs(engine, row_level_security=True),
    SqlCheckouts(engine, row_level_security=True),
    app,
)
```

The tables are `artifactr_files_blobs` and `artifactr_files_checkouts`, with their own Alembic version table, `artifactr_files_alembic_version`. A blob is 25 MiB at most unless the store is given a `limit`, up to 100 MiB, and larger bytes are refused with `TooLarge` as they arrive.

## Uploading a file

```python
from artifactr_files.blobs import once

outcome = await files.upload(
    ws, WordDocument, "contract.docx", once(data), media_type=DOCX
)
```

The bytes are put first, the app reads their outline, text, review and fingerprint, and then one `create_artifact` is committed. `upload` takes any async iterable of bytes, such as a request body. An agent's upload is a proposal, under the type's write policy.

## A person's check-out and check-in

```python
checkout = await files.check_out(ws, "a1")  # the lease, for eight hours
data = await files.read(ws, "a1")  # the head's bytes, to download
...
outcome = await files.check_in(ws, checkout.id, once(edited))
```

A check-out takes the artifact's lease as `checkout:<id>:<participant>`, records the version and digest checked out, and lasts eight hours unless it is extended with `files.extend(ws, checkout.id)`, which acquires the lease again. Nothing extends it in the background. Only the person who checked a file out checks it in or extends it.

A check-in reads its base from the check-out, never from the upload, takes the lease again, which renews one that lapsed if no one took it, and ends the check-out, releasing the lease:

- **Fresh:** a revision based on the version checked out, testing its digest, committed directly: write policies bind agents only.
- **Unchanged:** a file whose fingerprint is the head's commits nothing, and returns `None`. So a check-in retried after it succeeded does nothing; another file checked in on an ended check-out is refused with `InvalidState`, and so is extending it.
- **Stale:** if the lease lapsed and someone else took the file or committed meanwhile, the check-in is kept as a proposal against the head, with a test on the head's digest, and the check-out's digest as its provenance's base. A reviewer accepts or rejects it, as any proposal.

## An agent's edit

```python
outcome = await files.edit(
    agent_ws, "a1", base_version=3, commands=[AppCommand(name="add_paragraph", args={"text": "Fees"})],
    summary="Added the fees",
)
```

An agent's edit is a batch of the app's own commands. It holds the lease as `edit:<uuid>` for the app's call and the commit, 45 seconds by default and never renewed, and releases it however the call ends. The batch is kept as a blob, named in the revision's provenance with the app, its version and its build.

- **Busy:** while someone has the file checked out, the edit is refused with `ArtifactBusy`, whose `lease` says who. The agent plans again after the check-in, against the new head; if the `lease` is `None`, the lease ended in between, and it may try at once. It never queues a proposal that would be stale on arrival.
- **Stale:** an edit based on a version that isn't the head's is refused with `VersionConflict` before the app is called.
- **Accepted late:** accepting a proposal whose base has moved fails with `PatchFailed`. Its author makes a new one, based on the head.
- **Missing content:** a manifest can name bytes the store doesn't have, since any surface can commit `edit_artifact`. Reads raise `ContentUnavailable`, and edits are refused until the content is replaced.

The lease is advisory: artifactr's core doesn't know of it, so `edit_artifact` over REST or MCP isn't refused while someone holds it. The test and the base version are the guard, so such a write fails, or makes the next check-in stale; it is never silent.

## Reading a revision

`files.read(ws, artifact_id, version=None, part="content")` returns the bytes of the head or of a version, or its `text` or `review`. It resolves the artifact through the workspace first, which asks `authorize` and answers a restricted artifact as a missing one, and only then reads the bytes the revision names.

## Collecting what nothing names

```python
deleted = await files.collect(system_ws)
```

Bytes are put before the revision that names them is committed, so a failure in between leaves bytes no revision names. `collect` deletes the workspace's blobs that no pending proposal and no revision of a native file, archived ones included, names, unless they were put within `keep`, a day by default (`NativeFiles(..., keep=)`). Putting bytes again marks them as put now, so bytes about to be committed are kept. Run it per workspace, as an actor that sees everything there: it refuses a handle from which anything is hidden, whose reads would leave out what a hidden revision names.
