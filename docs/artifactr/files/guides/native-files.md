# Native files

A native file is an artifact whose data is a manifest over the file's bytes. This guide wires artifactr's `files` extra into an application and walks through what people and agents do with a file. Everything here runs with the fake app, and with WordCraft's adapter, [below](#wordcraft), in its place.

## The types

`WordDocument` is registered as `word_document` and holds `.docx` files (`DOCX`). Its manifest names three blobs, its content, its text and its review, and holds a fingerprint, an outline of up to 4,000 characters, its page count if known and its provenance:

```python
from artifactr.files import WordDocument

WordDocument.formats  # frozenset({DOCX})
WordDocument.write_policy  # "propose": an agent's edit is a proposal
```

A type for another format subclasses `NativeFile` and names its media types in `formats`; a manifest whose content isn't one of them doesn't validate. What the agent sees by default is the file's name, its pages if known and its outline: `render_for_agent` does no IO, so it shows what the app read from the file when the revision was made. The fingerprint is the digest of the content with what each save stamps, such as the time, left out, so a save that changes nothing else makes no revision.

## Wiring it in

`NativeFiles` takes a blob store, a check-out store and an app. Every method takes the `Workspace` to act in, so `authorize` and the hiding of restricted artifacts apply as for any read or command:

```python
from artifactr.files import FakeApp, InMemoryBlobs, InMemoryCheckouts, NativeFiles

files = NativeFiles(InMemoryBlobs(), InMemoryCheckouts(), FakeApp())
```

In production, both stores are SQL, with the `files` extra beside the `postgres` or `sqlite` one, as in `artifactr-ai[files,postgres]`. Migrate as the tables' owner; with row-level security, grant a role that owns nothing and give the stores its engine, as artifactr's storage has it:

```python
from artifactr.files.sql import SqlBlobs, SqlCheckouts, migrate

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
from artifactr.files.blobs import once

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

## WordCraft

`Subprocess` is WordCraft's adapter for `.docx`, with the `files` extra. It spawns WordCraft's CLI, `wordcraft-cli mcp`, for every call, in an empty directory that is the only place the CLI may read or write, and the call's process and directory end with it:

```python
from artifactr.files.wordcraft import Subprocess

app = Subprocess("/opt/wordcraft/bin/wordcraft-cli", version="0.7.0")
files = NativeFiles(blobs, checkouts, app)
```

A CLI that isn't `version` is refused, so the version a revision's provenance records is the one that ran. An agent's commands are WordCraft's own, such as `{"name": "text.insert", "args": {"text": "Fees"}}` or `{"name": "para.heading1"}`; `app.commands("comment")` finds them, ten at most, from the 617 it has. A batch stops at the first command that fails, which refuses it whole, naming the command.

The CLI runs as your application's user, with its network: `Subprocess` is for tests and trusted files; the worker, below, runs hostile ones. To fetch the pinned CLI, the one CI tests, run `scripts/craft wordcraft cli` in lattice: it downloads WordCraft's release once, checks its SHA-256 against `scripts/crafts/wordcraft.sha256`, and prints the CLI's path. `moon run artifactr:fidelity` runs the fidelity report with it.

## The worker

The worker runs an app on files you don't trust: one job at a time, behind a token, with each call's CLI under limits on its CPU time, address space and largest file, and limits on the deadline, the file sent and the reply. Each breach is an `AppFailed`, typed as any other. Run it in a container of its own, on a network with no route out, as stackr's recipe will (lattice RFC-0003); it reads its settings from the environment:

```bash
WORKER_TOKEN=$(openssl rand -hex 32) \
WORDCRAFT_CLI=/opt/wordcraft/bin/wordcraft-cli WORDCRAFT_VERSION=0.7.0 \
WORKER_BUILD=sha256:… WORKER_LIMITS='{"render": 5}' \
python -m artifactr.files.worker
```

`WORKER_LIMITS` sets any of `Limits`' fields, the rest their defaults. It listens on 127.0.0.1:8080 unless `WORKER_HOST` and `WORKER_PORT` say otherwise; inside its container, set `WORKER_HOST` to its address on the internal network, and nothing else. Your application calls it through `Worker`, an `App` like any other, whose version and build are the worker's, so a revision's provenance records the image that read it:

```python
from artifactr.files.worker import Worker

app = await Worker.connect("http://worker:8080", token=os.environ["WORKER_TOKEN"])
files = NativeFiles(blobs, checkouts, app)
```

A call that arrives while another runs waits its turn within its own deadline, so add containers, not jobs, to serve more. A `crashed` failure's message ends with what the CLI printed, which a hostile file can shape: log it, but don't show it to people or pass it to an agent as it is. `worker_app(app, token=, limits=)` serves any app, if you build your own image: make the app with `launcher=limits.launcher()` and `limit=limits.files`, and pass `trusted=True` to one whose CLI confines nothing, since the worker is its confinement.

## GridCraft

`artifactr.files.gridcraft.Subprocess` is GridCraft's adapter for `.xlsx` workbooks, of the type `Workbook`. GridCraft's CLI confines nothing, so the adapter is made only with `trusted=True`, for tests and files you trust, until the sandboxed worker runs it:

```python
from artifactr.files.gridcraft import Subprocess as GridCraft

gridcraft = GridCraft("/opt/gridcraft/bin/gridcraft-cli", version="0.8.0", trusted=True)
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Workbook: gridcraft})
```

An agent's commands are GridCraft's own, such as `{"name": "cell.set", "args": {"cell": "B2", "input": "=SUM(B3:B9)"}}`; `gridcraft.commands("sort")` finds them, with where each is in GridCraft's ribbon. Its server has no batch, so the adapter runs a batch's commands one at a time and stops at the first that fails, which refuses the batch, naming the command, and saves nothing. GridCraft would open a CSV, or another format it reads, whatever the file is named, and save it as a `.xlsx`; the adapter refuses a source that isn't a `.xlsx` before GridCraft reads it, so a check-in never converts a file. A workbook's outline is its sheets, the ranges they use and their tables, and its text each sheet's cells as GridCraft shows them. It renders no page headless, and lists no comments. `scripts/craft gridcraft cli` fetches the pinned CLI, and `CRAFT=gridcraft moon run artifactr:fidelity` runs its fidelity report: GridCraft 0.8.0 keeps every feature of its corpus.

## DeckCraft

`artifactr.files.deckcraft.Subprocess` is DeckCraft's adapter for `.pptx` decks, of the type `Presentation`. DeckCraft's CLI confines nothing too, so it is made only with `trusted=True`:

```python
from artifactr.files.deckcraft import Subprocess as DeckCraft

deckcraft = DeckCraft("/opt/deckcraft/bin/deckcraft-cli", version="0.7.0", trusted=True)
```

An agent's commands are DeckCraft's own, such as `{"name": "slide.new", "args": {"layout": "titleAndContent"}}` or `{"name": "comment.add", "args": {"text": "Check"}}`; a batch stops at the first that fails, which refuses it whole. A deck's outline is its slides' titles, numbered from 1; its text is each slide's shapes, tables and notes; its review is each slide's comments, and its pages are its slides, each of which `render` draws as a PNG. DeckCraft opens its own `.deckcraft` format whatever a file is named, so the adapter refuses a source that isn't a `.pptx` before DeckCraft reads it. Its second save of a file writes the same XML another way, so its fingerprint reads each XML part in its canonical form, and a save that changes nothing makes no revision. `CRAFT=deckcraft moon run artifactr:fidelity` runs its fidelity report: DeckCraft 0.7.0 keeps every feature of its corpus.

## The other crafting apps

`artifactr.files.craft.CRAFTS` declares every crafting app, as its pinned release offers it, and each is an integration of its own, `files:<name>`, off by default but WordCraft's:

| App | Its server's dialect | Its CLI confines files to | Kept as | Key |
|---|---|---|---|---|
| WordCraft | tools | a read and a write root | `.docx` | `files:wordcraft`, on |
| GridCraft | tools | nothing | `.xlsx` | `files:gridcraft` |
| DeckCraft | tools | nothing | `.pptx` | `files:deckcraft` |
| PdfCraft | commands | one root | `.pdf` | `files:pdfcraft` |
| CADCraft | tools | nothing | `.dxf`, `.dwg` | `files:cadcraft` |
| PhotoCraft | commands | a read and a write root | `.psd` | `files:photocraft` |
| VectorCraft | commands | a read and a write root | `.svg` | `files:vectorcraft` |
| DesignCraft | tools | a read and a write root | `.idml` | `files:designcraft` |
| FigCraft | tools | nothing | its adapter's | `files:figcraft` |
| FilmCraft | commands | nothing | exports only | `files:filmcraft` |
| EffectCraft | commands | a read and a write root | exports only | `files:effectcraft` |
| SoundCraft | tools | a read and a write root | exports only | `files:soundcraft` |
| LightCraft | commands | nothing | exports only | `files:lightcraft` |

An app's adapter subclasses `ToolsDialect` or `CommandsDialect`, which take the CLI, the `version` it must be, `arguments` for it after `mcp`, `trusted`, `limit` and `lookup`. A CLI that confines nothing reads and writes wherever your application's user can, so its adapter refuses to be made, with `ValueError`, unless you pass `trusted=True`, saying its files are trusted or your process is already confined. Run such an app only in the worker where people upload files you don't trust. FilmCraft, EffectCraft, SoundCraft and LightCraft keep projects that point at media outside them, so lattice keeps only what they render or export, one file at a time.

`scripts/craft <app> cli`, `web` or `notices` (the licence files in this machine's CLI asset) fetches any of them at its pin, in `scripts/crafts/<app>.sha256`, and `CRAFT=<app> moon run artifactr:fidelity` runs an app's fidelity report, from its corpus in `tests/files/corpus/<app>/`.

**One app for each native type.** Give `NativeFiles` a mapping, and each file is read, edited and switched by its type's app, or else its nearest base's ([ADR-0012](../adr/0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md)):

```python
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Workbook: gridcraft})
files.app_of(Workbook)  # gridcraft
```

**The gate.** An app's key is on by default only once it passes its own gate: its release pinned, its fidelity matrix green in Nightly, its hostile files each refused in time, its CLI confined (or the worker running it), and its notices read. WordCraft passes it; the others' keys stay off until theirs do ([ADR-0011](../adr/0011-a-gate-for-each-app.md)).

**Licences and notices.** Every app is `MIT OR Apache-2.0`, and its licence files and `NOTICE` travel with its CLI and its browser build; `scripts/craft <app> notices` lists those beside the CLI. PdfCraft's Linux tarballs also carry its OCR's two models, `text-detection.rten` and `text-recognition.rten`, by Robert Knight ([ocrs-models](https://github.com/robertknight/ocrs-models)), trained on HierText, under CC-BY-SA-4.0: whatever ships PdfCraft's CLI from them ships their `ATTRIBUTION.txt` and licence files with it, as `CRAFTS["pdfcraft"].notices` lists. Each app's brand licence lets the brand's marks appear only in its unmodified official builds, so they are served unchanged, and no key, name or document of yours should use the brand's name.

## Switching an app on and off

Each app is an integration of its own, `files:wordcraft` for WordCraft, `files:gridcraft` for GridCraft, which a workspace's admin switches through the shared Integrations switch (lattice ADR-0027). Give `NativeFiles` the same `Integrations` your application gives artifactr's gate, and the gate `files.key_of`:

```python
from artifactr.workspace import Workspaces, integration_gate

files = NativeFiles(blobs, checkouts, app, integrations=grants)
workspaces = Workspaces(storage, gate=integration_gate(grants, files.key_of))
```

While a file's app is off in a workspace, `NativeFiles` refuses to upload, check out, extend, check in or edit its files there, with `NotEnabled`, before it takes any lease, so a check-out made before it was switched off lapses on its own; and the gate refuses an edit of a native file on every other surface, REST and MCP included. Its files are still read and downloaded, and their history kept. Without `integrations`, every app is on.

## The agent's tools

```python
from pydantic_ai import Agent

from artifactr.agent import ArtifactWorkspace, Session
from artifactr.files import WordDocument
from artifactr.files.tools import native_file_tools

agent = Agent(
    model,
    deps_type=Session[None],
    toolsets=[native_file_tools(files)],
    capabilities=[ArtifactWorkspace(types=[WordDocument])],
)
```

The agent sees a native file's name, pages and outline through artifactr's own `read_artifact`, and gets more with these:

| Tool | What it does |
|---|---|
| `read_native(artifact_id, start)` | The file's words, 8,000 characters a call, saying where to read on |
| `read_review(artifact_id, start)` | Its comments and tracked changes, 50 a call, as the app gives them, with their ids |
| `find_commands(artifact_id, query)` | The commands of the file's app that mention a word, ten at most |
| `edit_native(artifact_id, base_version, commands, summary)` | One batch of the app's commands, as `files.edit` runs it |
| `view_page(artifact_id, page)` | One rendered page, as an image: only with `native_file_tools(files, view=True)` |

They are offered only while the app is on in the run's workspace. Under `WordDocument`'s `propose` policy, an agent's edit is a proposal. If a person has the file checked out, `edit_native` tells the agent who, and until when, and the agent plans again once it is checked in, rather than retrying; another agent's edit, holding it for seconds, is retried, and a stale `base_version` asks it to read the file again.

## Check-out and check-in over HTTP

With the `fastapi` extra as well, as `artifactr-ai[files,fastapi]`, mount `files_router` beside artifactr's router, with the same workspaces and `resolve_actor`:

```python
from artifactr.files.fastapi import editor_app, files_router

app.include_router(files_router(workspaces, files, resolve_actor=resolve_actor), prefix="/v1")
```

| Route | What it does |
|---|---|
| `GET /workspaces/{w}/files/{a}` | The head's name, type, size, outline and pages; whose check-out has it, until when, and its id to its own holder; the app's talk level; whether the app is on; and the largest check-in it takes |
| `POST /workspaces/{w}/files/{a}/checkouts` | Check it out (201), for eight hours |
| `POST /workspaces/{w}/checkouts/{c}/extension` | Extend the check-out |
| `PUT /workspaces/{w}/checkouts/{c}/file` | Check the edited file in, as the body: `applied`, `proposed` if stale, or `unchanged` |
| `GET /workspaces/{w}/files/{a}/versions/{v}/content` | A version's bytes, as an attachment |
| `GET /workspaces/{w}/files/{a}/versions/{v}/text` | A version's words, as plain text, as the app read them |
| `GET /workspaces/{w}/files/{a}/versions/{v}/pages/{p}` | A version's page, as a PNG |
| `GET /workspaces/{w}/proposals/{p}/text` | The words a proposal would give the file, such as a stale check-in's |
| `GET /workspaces/{w}/proposals/{p}/pages/{n}` | A page of what a proposal would make of the file, as a PNG |

A check-in larger than `limit` (`files_router(..., limit=)`: give it your blob store's, 25 MiB by default) is refused from its `Content-Length` with 413, before it is read. The app's failures are 422 for a file or a page it refuses, 413 for a file too large, and 503 for a timeout or a crash; everything else is artifactr's statuses, so a busy file and an app switched off are 409.

The person edits in the app's browser build, as released. Serve it with `editor_app`, on a host name of its own for which your portal sets no cookies, so it never sees a token:

```python
editor = editor_app(Path("/srv/wordcraft-web-0.7.0"))  # what `scripts/craft wordcraft web` prints
```

It adds headers only: a policy that runs the build's own code and its inline script by its hash, and reaches no other origin, with no framing; and caching for its hashed files. The check-out flow is then: check out, download the version, open it in the editor, edit, save it to disk, and check it in.

portalr's app does that flow on a native file's page: name the editor in `config.json`, by the app's integration, and the app opens it in a new tab as a person checks a file out, and never one on the portal's own origin ([portalr ADR-0049](../../../portalr/adr/0049-checking-a-native-file-out-and-in.md)):

```python
from portalr.fastapi import Site

site = Site(
    supabase_url="https://project.supabase.co",
    supabase_key="sb_publishable_x",
    editors={"files:wordcraft": "https://wordcraft.example.net/"},
)
```

Where people check in files you don't trust, give `NativeFiles` the `Worker`: through `Subprocess`, the server reads each check-in in the application's own process, which isolates nothing.

**A check-in keeps the file's format.** Send the file's own type as the check-in's `Content-Type`, or `application/octet-stream` if you don't know it. A file in another format than the one checked out, by its `Content-Type` or as its app reads it, is refused with 409, `invalid_state`, naming `checked_out` and `checked_in`, and never converted: upload it as a new file instead ([ADR-0012](../adr/0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md)).

### The shim, for a build with a host surface

GridCraft's, PdfCraft's and CADCraft's builds have a `?host=parent` bridge, on which a page of their own origin opens a file in them and hears each save and whether there are unsaved changes. Serve the editor with the shim, lattice's page beside the build, and frame it from your portal:

```python
editor = editor_app(build, craft=CRAFTS["gridcraft"], portal="https://portal.example")
```

The portal frames `https://<editor>/.lattice/shim.html`, and speaks to it by `postMessage`, at the editor's origin:

| Message | Way | Fields |
|---|---|---|
| `lattice:ready` | to the portal | `version`: the build is listening |
| `lattice:open` | to the shim | `name`, `bytes` (an `ArrayBuffer`): the checked-out file |
| `lattice:dirty` | to the portal | `dirty`: whether there are unsaved changes |
| `lattice:save` | to the portal | `name`, `bytes`: each file the build would download; check it in, with its type |
| `lattice:failed` | to the portal | `error`: the build couldn't start |

The shim hears only your portal's origin and its own frame, and the build may then be framed by its own origin and your portal, and by nothing else. Send `lattice:open` once the shim says `lattice:ready`. The app's talk level is `bridged`, level 1+: no commands reach the editor. A build with a JavaScript API takes `methods=`, those of it the portal may call by `lattice:call` `{ id, method, args }`, answered by `lattice:reply` ([ADR-0010](../adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)).

## Reading a revision

`files.read(ws, artifact_id, version=None, part="content")` returns the bytes of the head or of a version, or its `text` or `review`. It resolves the artifact through the workspace first, which asks `authorize` and answers a restricted artifact as a missing one, and only then reads the bytes the revision names.

## Collecting what nothing names

```python
deleted = await files.collect(system_ws)
```

Bytes are put before the revision that names them is committed, so a failure in between leaves bytes no revision names. `collect` deletes the workspace's blobs that no pending proposal and no revision of a native file, archived ones included, names, unless they were put within `keep`, a day by default (`NativeFiles(..., keep=)`). Putting bytes again marks them as put now, so bytes about to be committed are kept. Run it per workspace, as an actor that sees everything there: it refuses a handle from which anything is hidden, whose reads would leave out what a hidden revision names.
