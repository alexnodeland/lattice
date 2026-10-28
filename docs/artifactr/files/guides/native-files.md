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

The tables are `artifactr_files_blobs`, `artifactr_files_checkouts` and `artifactr_files_tenants`, with their own Alembic version table, `artifactr_files_alembic_version`. A blob is 25 MiB at most unless the store is given a `limit`, up to 100 MiB, and larger bytes are refused with `TooLarge` as they arrive.

Either store holds each workspace and each tenant to a quota, if given one, of bytes and of files (artifacts with bytes in the store); none by default. A put of new bytes past one is refused with `OverQuota`, which names the quota; `SqlBlobs` counts in the transaction that inserts, under a lock on the tenant's row, so puts at once never pass a quota together:

```python
from artifactr.files.blobs import Quota

SqlBlobs(
    engine,
    row_level_security=True,
    workspace_quota=Quota(bytes=2 << 30, files=1_000),
    tenant_quota=Quota(bytes=20 << 30),
)
```

## Uploading a file

```python
from artifactr.files.blobs import once

outcome = await files.upload(
    ws, WordDocument, "contract.docx", once(data), media_type=DOCX
)
```

The bytes are put first, the app reads their outline, text, review and fingerprint, and then one `create_artifact` is committed. `upload` takes any async iterable of bytes, such as a request body. An agent's upload is a proposal, under the type's write policy.

Without `media_type`, as for a person's upload, the format is told by the first bytes, never by what a client says: of the type's formats, the one whose signature they match (`FORMATS`), else `AppFailed("refused")` before anything is stored. Either way the name keeps no path or control character and takes the format's extension. Give an `artifact_id` to make a retry safe: an upload whose file with that id is already these bytes commits nothing and returns None. The app reads the file before anything is stored, and the file and what was read from it are then put together (`Blobs.put_all`), so a refused upload holds nothing against a quota. `NativeFiles(readings=2)`, the default, lets each tenant have two files read by the app at once, refusing a third with `Busy` ([ADR-0017](../adr/0017-a-persons-upload-told-by-its-bytes-read-before-it-is-committed.md)).

## Creating a blank file

```python
outcome = await files.create(ws, WordDocument, "Travel plan", thread_id=thread_id)
```

The app makes an empty file of the type, `apply(None, [])`, in one of the tenant's readings, and it is stored and committed as an upload is, held to the quotas, under a new id. Its format is the one the app names, or the type's only one, and its provenance's source is `blank`, naming the agent and run that asked when it is committed for one. Give an `artifact_id` to make a retry safe: a file of the type already there with that id makes nothing, before the app is called or the pace spent, and returns None. `create` asks `authorize` for `artifactr:create_native_file` and `artifactr:create_artifact` as the handle's actor before anything else. An agent's run commits the file as the person it acts for, so it is applied, not proposed; its edits of it then follow the type's write policy. A run for no one, or for a person's client, commits it under the policy.

`NativeFiles(pace=Pace(20), gauge=Gauge(8, tenant=4, each=2))` holds each person to a pace of files a minute and this process to so many at once, refusing another with `Paced`; `files_router` then uses them for uploads and check-ins too, in place of its own, so an agent's files and a person's count together. Without them, `create` is held only to the readings ([ADR-0019](../adr/0019-the-agent-creates-native-files.md)).

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

app = Subprocess("/opt/wordcraft/bin/wordcraft-cli", version="0.11.0")
files = NativeFiles(blobs, checkouts, app)
```

A CLI that isn't `version` is refused, so the version a revision's provenance records is the one that ran. An agent's commands are WordCraft's own, such as `{"name": "text.insert", "args": {"text": "Fees"}}` or `{"name": "para.heading1"}`; `app.commands("comment")` finds them, ten at most, from the 643 it has at 0.11.0, less those that start with `file.` or `app.`, which reach past the open file: a batch that holds one is refused before any runs, and the search never finds one. A batch stops at the first command that fails, which refuses it whole, naming the command.

The CLI runs as your application's user, with its network: `Subprocess` is for tests and trusted files; the worker, below, runs hostile ones. To fetch the pinned CLI, the one CI tests, run `scripts/craft wordcraft cli` in lattice: it downloads WordCraft's release once, checks its SHA-256 against `scripts/crafts/wordcraft.sha256`, and prints the CLI's path. `moon run artifactr:fidelity` runs the fidelity report with it.

## The worker

The worker runs an app on files you don't trust: one job at a time, behind a token, with each call's CLI under limits on its CPU time, address space and largest file, and limits on the deadline, the file sent and the reply. Each breach is an `AppFailed`, typed as any other. Run it in a container of its own, on a network with no route out, as stackr's template does ([stackr ADR-0043](../../../stackr/adr/0043-native-files-in-the-template.md)); it runs one app, `WORKER_APP`, any whose files lattice keeps, and reads its settings from the environment:

```bash
WORKER_TOKEN=$(openssl rand -hex 32) WORKER_APP=gridcraft \
WORKER_CLI=/opt/gridcraft/bin/gridcraft-cli WORKER_VERSION=0.8.0 \
WORKER_BUILD=sha256:… WORKER_LIMITS='{"render": 5}' \
python -m artifactr.files.worker
```

`WORKER_APP` is `wordcraft` unless set. The CLI starts under the limits' launcher, and an app whose CLI confines nothing runs trusted, since the worker is its confinement. `WORKER_LIMITS` sets any of `Limits`' fields, the rest their defaults. It listens on 127.0.0.1:8080 unless `WORKER_HOST` and `WORKER_PORT` say otherwise; inside its container, set `WORKER_HOST` to its address on the internal network, and nothing else. Your application calls it through `Worker`, an `App` like any other, whose version and build are the worker's, so a revision's provenance records the image that read it:

```python
from artifactr.files.worker import Worker

app = await Worker.connect("http://worker:8080", token=os.environ["WORKER_TOKEN"])
files = NativeFiles(blobs, checkouts, app)
```

An application that builds `NativeFiles` and its routes before its event loop runs makes the app with `Worker.at`, which asks nothing yet, and opens it as it starts; until then, its name and version raise:

```python
app = Worker.at("http://worker:8080", token=os.environ["WORKER_TOKEN"])
files = NativeFiles(blobs, checkouts, {Workbook: app})
...
await app.open()  # in the application's lifespan, before any request
```

A call that arrives while another runs waits its turn within its own deadline, so add containers, not jobs, to serve more. A `crashed` failure's message ends with what the CLI printed, which a hostile file can shape: log it, but don't show it to people or pass it to an agent as it is. `worker_app(app, token=, limits=)` serves any app, if you build your own image: make the app with `launcher=limits.launcher()` and `limit=limits.files`, and pass `trusted=True` to one whose CLI confines nothing, since the worker is its confinement.

## GridCraft

`artifactr.files.gridcraft.Subprocess` is GridCraft's adapter for `.xlsx` workbooks, of the type `Workbook`. GridCraft's CLI confines nothing, so the adapter is made only with `trusted=True`, for tests and files you trust, until the sandboxed worker runs it:

```python
from artifactr.files.gridcraft import Subprocess as GridCraft

gridcraft = GridCraft("/opt/gridcraft/bin/gridcraft-cli", version="0.8.0", trusted=True)
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Workbook: gridcraft})
```

An agent's commands are GridCraft's own, such as `{"name": "cell.set", "args": {"cell": "B2", "input": "=SUM(B3:B9)"}}`; `gridcraft.commands("sort")` finds them, with where each is in GridCraft's ribbon. Its server has no batch, so the adapter runs a batch's commands one at a time and stops at the first that fails, which refuses the batch, naming the command, and saves nothing. GridCraft would open a CSV, or another format it reads, whatever the file is named, and save it as a `.xlsx`; the adapter refuses a source that isn't a `.xlsx` before GridCraft reads it, so a check-in never converts a file. A workbook's outline is its sheets, the ranges they use and their tables, and its text each sheet's cells as GridCraft shows them. It renders no page headless, and lists no comments. `scripts/craft gridcraft cli` fetches the pinned CLI, and `CRAFT=gridcraft moon run artifactr:fidelity` runs its fidelity report: GridCraft 0.8.0 keeps every feature of its corpus; not covered by the corpus: charts, pivots, images, sparklines and data bars.

## DeckCraft

`artifactr.files.deckcraft.Subprocess` is DeckCraft's adapter for `.pptx` decks, of the type `Presentation`. DeckCraft's CLI confines nothing too, so it is made only with `trusted=True`:

```python
from artifactr.files.deckcraft import Subprocess as DeckCraft

deckcraft = DeckCraft("/opt/deckcraft/bin/deckcraft-cli", version="0.7.0", trusted=True)
```

An agent's commands are DeckCraft's own, such as `{"name": "slide.new", "args": {"layout": "titleAndContent"}}` or `{"name": "comment.add", "args": {"text": "Check"}}`; a batch stops at the first that fails, which refuses it whole. A deck's outline is its slides' titles, numbered from 1; its text is each slide's shapes, tables and notes; its review is each slide's comments, and its pages are its slides, each of which `render` draws as a PNG. DeckCraft opens its own `.deckcraft` format whatever a file is named, so the adapter refuses a source that isn't a `.pptx` before DeckCraft reads it. Its second save of a file writes the same XML another way, so its fingerprint reads each XML part in its canonical form, and a save that changes nothing makes no revision. `CRAFT=deckcraft moon run artifactr:fidelity` runs its fidelity report: DeckCraft 0.7.0 keeps every feature of its corpus; not covered by the corpus: charts, masters and layouts beyond one, embedded media and animations. What the adapter reads of a deck's XML in its canonical form is bounded: 16 MiB a part, 500,000 elements in all, 256 deep; past that the file is refused.

## PdfCraft

`artifactr.files.pdfcraft.Subprocess` is PdfCraft's adapter for `.pdf` documents, of the type `PdfDocument`. Its CLI takes one root, so, as WordCraft's, it is confined to the call's own directory, and needs no `trusted`:

```python
from artifactr.files.pdfcraft import Subprocess as PdfCraft

pdfcraft = PdfCraft("/opt/pdfcraft/bin/pdfcraft-cli", version="0.8.0")
```

An agent's commands are PdfCraft's own, run through its command registry, such as `{"name": "page.insert_blank", "args": {"at": 2}}`; the adapter names the open document in each, and a batch stops at the first that fails, which refuses it whole. A document's outline is its bookmarks, its text each page's, its review its comments, and its pages its pages, each of which `render` draws as a PNG. PdfCraft stamps the time on every save, so the fingerprint leaves the stamp out, and a save that changes nothing else makes no revision. A document PdfCraft can only read by repairing it, such as one cut short, is refused rather than saved as PdfCraft's repair. `CRAFT=pdfcraft moon run artifactr:fidelity` runs its fidelity report: PdfCraft 0.8.0 keeps every feature of its corpus; not covered by the corpus: signatures (which PdfCraft's full rewrite on save invalidates), annotations beyond text notes and links, encryption, XFA and incremental updates. The fingerprint reads the file in one pass and inflates object streams only up to `limit`. Its key stays off until it passes its gate; the notices its Linux tarballs carry are below.

## The other crafting apps

`artifactr.files.craft.CRAFTS` declares every crafting app, as its pinned release offers it, and FreeCAD and Blender, below; each is an integration of its own, `files:<name>`, off by default but WordCraft's:

| App | Its dialect | Its CLI confines files to | Kept as | Key |
|---|---|---|---|---|
| WordCraft | tools | a read and a write root | `.docx` | `files:wordcraft`, on |
| GridCraft | tools | nothing | `.xlsx` | `files:gridcraft` |
| DeckCraft | tools | nothing | `.pptx` | `files:deckcraft` |
| PdfCraft | commands | one root | `.pdf` | `files:pdfcraft` |
| CADCraft | tools | nothing | `.dxf`, `.dwg` | `files:cadcraft` |
| PhotoCraft | commands | a read and a write root | `.psd` | `files:photocraft` |
| VectorCraft | commands | a read and a write root | `.svg` | `files:vectorcraft` |
| DesignCraft | tools | a read and a write root | `.idml` | `files:designcraft` |
| FigCraft | tools | nothing | `.figcraft` | `files:figcraft` |
| FreeCAD | script | nothing | `.FCStd` | `files:freecad` |
| Blender | script | nothing | `.blend` | `files:blender` |
| FilmCraft | commands | nothing | `.fcproj` that holds its own media | `files:filmcraft` |
| EffectCraft | commands | a read and a write root | `.ecproj` that holds no footage | `files:effectcraft` |
| SoundCraft | tools | a read and a write root | `.scraft` that holds no audio | `files:soundcraft` |
| LightCraft | commands | nothing | nothing yet | `files:lightcraft` |

A crafting app's adapter subclasses `ToolsDialect` or `CommandsDialect`, its MCP server's dialect, which take the CLI, the `version` it must be, `arguments` for it after `mcp`, `trusted`, `limit` and `lookup`. A CLI that confines nothing reads and writes wherever your application's user can, so its adapter refuses to be made, with `ValueError`, unless you pass `trusted=True`, saying its files are trusted or your process is already confined. Run such an app only in the worker where people upload files you don't trust. FilmCraft, EffectCraft and SoundCraft keep projects that may point at media outside them, so lattice keeps a project only whole, holding every medium it draws, and nothing it exports, each below; LightCraft's work is a library and sidecars, never one file, so it has no adapter ([ADR-0016](../adr/0016-a-project-that-holds-its-own-media-is-a-native-file.md)).

`scripts/craft <app> cli`, `web` or `notices` (the licence files in this machine's CLI asset) fetches any of them at its pin, in `scripts/crafts/<app>.sha256`, and `CRAFT=<app> moon run artifactr:fidelity` runs an app's fidelity report, from its corpus in `tests/files/corpus/<app>/`.

**Each app's adapter.** An app with an adapter has a package of its own beside WordCraft's, `artifactr.files.<app>`, whose `Subprocess` is the adapter, and a native type its files are kept as. Each reads a file's format from the file itself and saves it in that format, so no edit converts it ([ADR-0012](../adr/0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md)), and each has a fidelity corpus of its own.

- **CADCraft** keeps drawings, `Drawing`, `.dxf` and `.dwg`, and its CLI confines nothing, so its adapter is made with `trusted=True`: run it in the worker, above, where files aren't trusted. A drawing is opened in the format its first bytes say, and saved in it, so a DWG stays a DWG. Those bytes are a DWG's version, `AC10` and two digits, a binary DXF's sentinel, or an ASCII DXF's first group, `0` then `SECTION`, its lines ended by LF or CRLF; a DXF whose lines end in CR alone, or with spaces after `SECTION`, and a DWG of another version, are refused. Its server has no batch, so the commands, such as `{"name": "line", "args": {"points": [[0, 0], [10, 0]]}}`, run one at a time through its `execute`, and the first that fails refuses the batch before anything is saved. Its outline is the model space's entities by type, its layers and its layouts, its text is the drawing's texts, and it renders its model space, fitted to its extents, as page 1. Its corpus is of DXF, written by hand; its live tests open and save a DWG of CADCraft's own making. Its browser build has a `?host=parent` bridge, so it talks through the shim. ADR-0012 records that build as saving DXF only, which no test here holds: if so, a DWG saved in it comes back a DXF, which the check-in refuses as `FormatChanged`, never converts.

- **PhotoCraft** keeps layered images, `LayeredImage`, `.psd`, and its CLI takes a read and a write root. It refuses `file.open`, so a file is opened, made and saved through its own tools, `doc_open`, `doc_new` and `doc_save`, and its commands act on the document open last. A file is opened only if its header says it is a `.psd`: a `.psb`, its large form, is refused, since saving it as a `.psd` would convert it. Its outline is its layers, top to bottom and indented by group, its text is its type layers' words, its review is its notes, and it renders the flattened image as page 1. Its corpus is six features written by hand, which 0.9.0 keeps; type layers are left to its live tests, since their descriptors are impractical to write by hand. Its browser build has no host surface, so a person downloads and uploads its files.

- **VectorCraft** keeps vector images, `VectorImage`, `.svg`, and its CLI takes a read and a write root. VectorCraft opens PDF, Illustrator, EPS and more and would save any of them as an SVG, so a file whose root element isn't `svg` is refused before the CLI starts. Its commands act on the document open last, which none of them names. Its outline is its layers and groups, its text is its type objects' words, top to bottom, and each artboard is a page, rendered by `render_preview`. A save writes every shape as a path, bakes transforms into the geometry, and sets the SVG's `<title>` to the file's name: a title isn't kept. Its browser build has no host surface, so a person downloads and uploads its files.

- **DesignCraft** keeps page layouts, `PageLayout`, `.idml`, and its CLI takes a read and a write root. Its own save writes its native format, so a layout is opened and saved as IDML by its commands, `file.openIdml` and `file.exportIdml`, and anything else, its own format or an `.indd` it would convert, is refused before it is opened. Its batch names the command that failed, its outline is each story's first line, its text is its stories' words, and it renders each page, numbered from 1. Its corpus is seven IDML features written by hand. A table's words are kept, but a table's first save isn't a fixpoint, so no corpus file holds one, and a new layout's ids are numbered again on its next save: each costs one revision more. Its browser build has no host surface, so a person downloads and uploads its files.

- **FilmCraft** keeps video projects, `VideoProject`, `.fcproj`, JSON under `FCPROJ`, a media type of lattice's naming. Its CLI confines nothing, so its adapter is made with `trusted=True`: run it in the worker, above, where files aren't trusted. A project is kept only whole: one that draws on a file outside it, an imported medium, a proxy, or a LUT from a file or the user's library, is refused by name before FilmCraft opens it, and so is a batch that brings one in; a batch runs no command that opens, saves, imports or exports a file, and none given a path. Its media are its generators': bars and tone, mattes, black video, titles, shapes, captions and its demo footage. One FilmCraft would migrate from an older release, or says misses media, is refused too, as a save would change it. A blank project is an empty, untitled one. Its outline is its bins and items, then its active sequence's tracks and their clips; its text is its captions' words, its review its sequence's markers, and each second of the sequence is a page, the frame at its start rendered by `render_preview`. What FilmCraft exports from a project, a video, audio or stills, isn't kept. Its corpus is thirteen features, each made by FilmCraft from a script of its own commands, which 0.8.0 keeps; `python -m tests.files.corpus.filmcraft.make CLI` makes them again. Its browser build has no host surface, so a person downloads and uploads its files.

- **EffectCraft** keeps motion graphics, `MotionGraphics`, `.ecproj`, JSON under `ECPROJ`, a media type of lattice's naming, and its CLI takes a read and a write root, which also stop its JavaScript, `script.run`. A project is kept only whole: its items are compositions, solids and folders, and one with footage, an image, video, audio or a 3D model named by path, is refused by name before EffectCraft opens it, and so is a batch that imports one. One EffectCraft had to repair to open, such as a composition too large or too fast for it, is refused, as a save would write the repair. A blank project is an empty, untitled one. Its outline is its items, indented by folder, then its active composition's layers; its text is the words of that composition's first 100 text layers, each read by a call of its own, its review its markers, and each second of the composition is a page, the frame at its start rendered by `render_preview`. What EffectCraft renders from a project isn't kept. Its corpus is thirteen features, each made by EffectCraft from a script of its own commands, which 0.11.1 keeps; an expression, JavaScript its Boa engine runs, that loops forever is ended by EffectCraft's own limit, which isn't confinement, so a project from someone you don't trust runs in the worker; and an older schema is opened and saved in the current one. Its browser build has a JavaScript API, `window.effectcraft`, which no pilot has run through the shim, so a person downloads and uploads its files.

- **SoundCraft** keeps audio sessions, `AudioSession`, `.scraft`, JSON under `SCRAFT`, a media type of lattice's naming, and its CLI takes a read and a write root. A session is kept only whole: its MIDI and SoundCraft's built-in instruments and effects are its own, and one with audio, recorded, imported or in its sampler, or video, which a save writes as files beside it, is refused by name before SoundCraft opens it, as is one naming a plugin of another maker's, a VST3, CLAP or Audio Unit, which SoundCraft would load from the machine. A batch runs no command of SoundCraft's engine's or app's, such as a scan for plugins, and names no plugin of another maker's, and one that brings in audio is refused. One SoundCraft says misses media is refused too. A blank session is an empty, untitled one. Its batch takes its commands as `calls`, and stops at the first that fails. Its outline is its tracks, their kinds and clips, and its busses; its text is its tracks' comments, and its review its markers. It renders no page headless, so a session has none, and what SoundCraft mixes down from it isn't kept. Its corpus is ten features, each made by SoundCraft from a script of its own commands, which 0.8.0 keeps. Its browser build has no host surface, so a person downloads and uploads its files.

- **LightCraft** has no adapter, and lattice keeps none of its files. It never writes a photo it develops: its edits live in its library, a folder, or in an XMP sidecar beside the photo, and a photo it exports is rendered with the edit baked in, and keeps no edit LightCraft can open again ([ADR-0016](../adr/0016-a-project-that-holds-its-own-media-is-a-native-file.md)). Its key stays off.

- **FigCraft** keeps designs, `Design`, `.figcraft`, a zip holding its document as JSON, under `FIGCRAFT`, a media type of lattice's naming since it has no registered one. Its CLI confines nothing, so its adapter is made with `trusted=True`: run it in the worker, above, where files aren't trusted. Only a file whose document says it is a `.figcraft`, its `format` first, as FigCraft writes it, is opened (a live test fails if a release writes it otherwise): FigCraft would open a `.fig`, its JSON, an SVG or an image and save it as a `.figcraft`, so those are refused before it starts. A blank design is the untitled one its server starts with. Its batch is one undo step that FigCraft rolls back whole when a command fails. Its outline is its pages and their layers, its text is its text layers' words, and its review is its comments. Each canvas page is a page, drawn by going to it and taking its `screenshot`; an empty page, which FigCraft refuses to draw, is drawn as its background alone, a square, so a blank design's page renders (seen with the macOS CLI; the Linux CLI's refusal is unverified) ([ADR-0009](../adr/0009-each-crafting-app-declared-once-on-one-of-two-dialects.md)). Its browser build has no host surface, so a person downloads and uploads its files.

```python
from artifactr.files import Drawing
from artifactr.files.cadcraft import Subprocess as CADCraft

cadcraft = CADCraft("/opt/cadcraft/bin/cadcraft-cli", version="0.8.0", trusted=True)
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Drawing: cadcraft})
```

**One app for each native type.** Give `NativeFiles` a mapping, and each file is read, edited and switched by its type's app, or else its nearest base's ([ADR-0012](../adr/0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md)):

```python
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Workbook: gridcraft})
files.app_of(Workbook)  # gridcraft
```

**The gate.** An app's key is on by default only once it passes its own gate: its release pinned, its fidelity matrix green in Nightly, its hostile files each refused in time, its CLI confined (or the worker running it), and its notices read. WordCraft passes it; the others' keys stay off until theirs do ([ADR-0011](../adr/0011-a-gate-for-each-app.md)).

**Licences and notices.** Every storytold app is `MIT OR Apache-2.0`, and its licence files and `NOTICE` travel with its CLI and its browser build; `scripts/craft <app> notices` lists those beside the CLI. PdfCraft's Linux tarballs also carry its OCR's two models, `text-detection.rten` and `text-recognition.rten`, by Robert Knight ([ocrs-models](https://github.com/robertknight/ocrs-models)), trained on HierText, under CC-BY-SA-4.0: whatever ships PdfCraft's CLI from them ships their `ATTRIBUTION.txt` and licence files with it, as `CRAFTS["pdfcraft"].notices` lists. Each app's brand licence lets the brand's marks appear only in its unmodified official builds, so they are served unchanged, and no key, name or document of yours should use the brand's name.

## FreeCAD

FreeCAD is the FreeCAD project's parametric 3D modeller, under LGPL-2.1-or-later, not one of the crafting apps, and its key is `files:freecad`, off by default. It keeps 3D models, `CadModel`, `.FCStd`, under `FCSTD`, `application/x-extension-fcstd`, the media type FreeCAD's own MIME file gives it ([ADR-0014](../adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md)). It has no server: its adapter runs FreeCAD's console, `freecadcmd`, on a script of its own for every call, with the call as JSON, in a directory of the call's own, with nothing of your environment and no user macro, addon or setting (`--safe-mode`). The script reads and writes wherever your user can, so the adapter is made with `trusted=True`: run it in the worker where files aren't trusted.

```python
from artifactr.files import CadModel
from artifactr.files.freecad import Subprocess as FreeCAD

freecad = FreeCAD(cli, version="1.1.4", trusted=True)  # cli: from scripts/craft freecad cli
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, CadModel: freecad})
```

**What FreeCAD is given.** Opening a document in FreeCAD restores a Python feature by importing the module it names, so before FreeCAD starts, the adapter reads every part of the zip, inflating each against the limit whatever its header says, and gives FreeCAD a fresh zip it rebuilt from those parts, `Document.xml` first, never the bytes it was sent. A part no property names is refused, as is a model of more than 1,000 parts, and the GUI's camera is emptied, so a file's view isn't kept. It refuses a document with a part named twice or out of its folder, a part that isn't a regular file, bytes before its first part, a DTD, XML nested more than 256 deep or more than 1,000 parts; and one whose objects, extensions or properties are of a type outside those its commands and corpus make, so a Python feature, an included file, a path or a link to another file is refused, as is an expression or a cell that names another document (a `#`). That refuses every Draft, BIM and addon file: keep such a file as an upload. FreeCAD 1.1.4's own restore refuses a pickled proxy and any module outside FreeCAD's own behind it, which a live test holds; a cycle in objects' links is refused by the script once FreeCAD has opened the file. The scan isn't FreeCAD's reader, and a shape's `.brp`, which OpenCASCADE parses, isn't scanned: run FreeCAD in the worker for files you don't trust, once your image has it.

**The commands are lattice's.** An agent's commands are a fixed set the script carries out through FreeCAD's document API, none of them Python: `box`, `cylinder`, `sphere`, `cone`, `boolean` (`cut`, `fuse`, `common`), `sketch`, `sketch.line`, `sketch.circle`, `sketch.constraint`, `extrude`, `move`, `set`, `remove`, `sheet`, `sheet.set` and `sheet.alias`, such as `{"name": "box", "args": {"length": 20, "width": 10, "height": 5}}`. `app.commands("sketch")` finds them with no CLI started. Each argument is checked by its type; `set` writes a number, a string or a boolean to a property its object already has. A batch is recomputed, an object it leaves invalid refuses it, and a batch's document is saved as a reopened one is, so its next save is a fixpoint.

**What a save keeps.** A document is saved under the label it had, with no recompute when no command ran, so its shapes' bytes are kept; the console drops `GuiDocument.xml`, which holds colours and visibility, so the adapter puts the source's back, and the thumbnail is dropped. The fingerprint is every part's bytes, with the time each save writes left out. The outline is each object's label and type, a line each, and the text is the sheets' cells. Page 1 is the model drawn isometrically, its visible edges in black; a model with no shape is refused. Its corpus is nine features made by FreeCAD itself, each kept by 1.1.4.

`scripts/craft freecad cli` fetches FreeCAD's Linux AppImage for this machine, checks it against `scripts/crafts/freecad.sha256`, unpacks it, and prints its `freecadcmd`; there is no macOS CLI and no browser build, so a person edits a model in their own FreeCAD, and downloads and uploads it. `notices` lists the licence files the AppImage carries.

## Blender

Blender is the Blender Foundation's 3D creation suite, under GPL-3.0, not one of the crafting apps, and its key is `files:blender`, off by default. It keeps 3D scenes, `Scene`, `.blend`, under `BLEND`, `application/x-blender`, the shared MIME-info database's name for it ([ADR-0015](../adr/0015-blender-on-the-script-dialect-and-no-file-that-may-run-python.md)). lattice runs Blender only as a separate process, and never imports `bpy`: its adapter starts `blender --background` on a script of its own for every call, as FreeCAD's does, with no user setting or startup file (`--factory-startup`), no script a file holds (`--disable-autoexec`) and no network (`--offline-mode`). The script reads and writes wherever your user can, so the adapter is made with `trusted=True`: run it in the worker where files aren't trusted, with an address space of at least 4 GiB (`Limits(memory=4 << 30)`), since Blender crashed under the worker's default 2 GiB: the worker refuses to start it under less. Whoever ships Blender in an image ships it under the GPL-3.0.

```python
from artifactr.files import Scene
from artifactr.files.blender import Subprocess as Blender

blender = Blender(cli, version="5.2.2", trusted=True)  # cli: from scripts/craft blender cli
files = NativeFiles(blobs, checkouts, {WordDocument: wordcraft, Scene: blender})
```

**What Blender is given.** A `.blend` is Blender's memory written out, block by block, and Blender reads a block through a pointer by its size alone, whatever struct it is. So before Blender starts, in a thread under the call's deadline, the adapter inflates the file's zstd against the limit, holds its header, versions and catalogue of structs to Blender 5.2's own, and reads every block: it refuses a text, a library, an image, a font, a sound, a node group or any data-block but cameras, collections, lights, materials, meshes, objects, scenes and the windows every file holds; a block of a struct outside those 5.2 saves for what the commands make, so a driver, animation or a packed file, or of another struct than its code's; an address twice where Blender maps addresses; any pointer that resolves, by its kind (a struct, a list, `void *`, an array of pointers, plain data, runtime state), to what its field may not hold; an object whose data isn't its type's; a node other than a new material's or light's; a script node's name in any block; a head that lies, too many blocks, bytes after the end, and more work than a scan may take. Blender is given the blocks it read, written again uncompressed without the thumbnail, never the bytes it was sent, and the script refuses again what Blender opened with a data-block of any other kind, animation, a cycle of parents or modifiers past their bounds, and draws with compositing, the sequencer and Freestyle off. That refuses most files with animation, images or node groups: keep such a file as an upload. The scan isn't Blender's reader, which still reads every allowed struct's other fields.

**The commands are lattice's.** An agent's commands are a fixed set the script carries out through Blender's data API, none of them Python: `cube`, `sphere`, `cylinder`, `cone`, `plane`, `move`, `material`, `assign`, `modifier` (`subdivision`, `bevel`, `array`, `mirror`, `solidify`), `camera`, `light`, `collection`, `link`, `render`, `set` and `remove`, such as `{"name": "cube", "args": {"size": 2, "at": [0, 0, 1]}}`. `app.commands("material")` finds them with no CLI started. Each argument is checked by its type and its bounds, and a batch is saved as a reopened file is, so its next save is a fixpoint.

**What a save keeps.** A file is saved compressed if it came compressed, and a blank one compressed, as Blender's GUI saves. The fingerprint is every block but the thumbnail, uncompressed, with the three fields each save stamps (the file's path, the file browser's folder and a profile's counter) left out. The outline is each object's name, type and collections, a line each, and the text is the materials. Page 1 is the scene drawn through its camera by Workbench, with no GPU; a scene with no camera is refused. Its corpus is seven features made by Blender itself, each kept by 5.2.2.

`scripts/craft blender cli` fetches Blender's Linux x86_64 tarball from download.blender.org, checks it against `scripts/crafts/blender.sha256`, unpacks it, and prints its `blender`. Blender releases no Linux aarch64 build, and its macOS one is a disk image, so there is no CLI on either and no browser build: a person edits a scene in their own Blender, and downloads and uploads it. `notices` lists the tarball's `license/` and `copyright.txt`.

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
| `create_native_file(type, title)` | A blank file of one of the types listed, those whose app is on in the workspace, as `files.create` makes it |
| `read_native(artifact_id, start)` | The file's words, 8,000 characters a call, saying where to read on |
| `read_review(artifact_id, start)` | Its comments and tracked changes, 50 a call, as the app gives them, with their ids |
| `find_commands(artifact_id, query)` | The commands of the file's app that mention a word, ten at most |
| `edit_native(artifact_id, base_version, commands, summary)` | One batch of the app's commands, as `files.edit` runs it |
| `view_page(artifact_id, page)` | One rendered page, as an image: only with `native_file_tools(files, view=True)` |

They are offered only while the app is on in the run's workspace. `create_native_file` lists the types whose app is on there, each with its extensions and what it is called, such as `- word_document (.docx): a Word document`, and answers `Created <id>: ... It is empty: edit it with edit_native.`, adding that a proposed edit waits for a person's review and the file stays empty until it is accepted, and follows the file. The file's id comes from the run and the call, so a retried call makes one file, and a run creates ten at most (`native_file_tools(files, creates=10)`); a refusal, such as a pace passed, a quota or a craft that can't make a blank file, is told in a sentence. Under `WordDocument`'s `propose` policy, the agent's edit is a proposal, of a file it created too. If a person has the file checked out, `edit_native` tells the agent who, and until when, and the agent plans again once it is checked in, rather than retrying; another agent's edit, holding it for seconds, is retried, and a stale `base_version` asks it to read the file again.

## Check-out and check-in over HTTP

With the `fastapi` extra as well, as `artifactr-ai[files,fastapi]`, mount `files_router` beside artifactr's router, with the same workspaces and `resolve_actor`:

```python
from artifactr.files.fastapi import editor_app, files_router

app.include_router(files_router(workspaces, files, resolve_actor=resolve_actor), prefix="/v1")
```

| Route | What it does |
|---|---|
| `GET /workspaces/{w}/uploads` | Whether the person may upload, the largest file, and each native type's extensions and whether its app is on |
| `POST /workspaces/{w}/files?kind=&name=` | Upload a file as a new native file of `kind`, as the body (201), or `unchanged` (200) when sent again with the same `artifact_id` |
| `GET /workspaces/{w}/files/{a}` | The head's name, type, size, outline and pages; whose check-out has it, until when, and its id to its own holder; the app's talk level; whether the app is on; and the largest check-in it takes |
| `POST /workspaces/{w}/files/{a}/checkouts` | Check it out (201), for eight hours |
| `POST /workspaces/{w}/checkouts/{c}/extension` | Extend the check-out |
| `PUT /workspaces/{w}/checkouts/{c}/file` | Check the edited file in, as the body: `applied`, `proposed` if stale, or `unchanged` |
| `GET /workspaces/{w}/files/{a}/versions/{v}/content` | A version's bytes, as an attachment |
| `GET /workspaces/{w}/files/{a}/versions/{v}/text` | A version's words, as plain text, as the app read them |
| `GET /workspaces/{w}/files/{a}/versions/{v}/pages/{p}` | A version's page, as a PNG |
| `GET /workspaces/{w}/proposals/{p}/text` | The words a proposal would give the file, such as a stale check-in's |
| `GET /workspaces/{w}/proposals/{p}/pages/{n}` | A page of what a proposal would make of the file, as a PNG |

An upload or a check-in larger than `limit` (`files_router(..., limit=)`: the blob store's unless smaller, 25 MiB by default) is refused from its `Content-Length` with 413, before it is read, and as it streams, whatever its `Content-Length` said. One past its format's own most, below the store's, such as a crafting app's 2 MiB JSON project, is refused as it streams too, an upload or a check-in; an upload, which names its kind, also from its `Content-Length`, and `GET /uploads` gives each kind's `limit`. The app's failures are 422 for a file or a page it refuses, 413 for a file too large, and 503 for a timeout or a crash, each with a sentence of the route's, never the app's own message, which goes to the `artifactr.files` log; a quota passed is 413, `over_quota`; a body slower than `Body` allows (a 30-second pause, 32 KiB a second) is 408; a person past their pace (`uploads_per_minute`, 20 by default), a tenant with all its readings, or a process with `uploads_at_once` (8) running, a tenant with `uploads_per_tenant` (4), or a person with `uploads_each` (2), past any of which is 429, with `Retry-After`; a check-in is held to the same; everything else is artifactr's statuses, so a busy file and an app switched off are 409.

An upload asks `authorize` for `artifactr:create_native_file`, an editor's in grantr, before it reads a byte; its `Content-Type` is never read. Every upload is recorded on the `artifactr.files.uploads` logger, as `extra={"upload": {...}}`: the actor, tenant, workspace, kind, digest and size, and how it ended.

The person edits in the app's browser build, as released. Serve it with `editor_app`, on a host name of its own for which your portal sets no cookies, so it never sees a token:

```python
editor = editor_app(Path("/srv/wordcraft-web-0.11.0"))  # what `scripts/craft wordcraft web` prints
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

WordCraft's, GridCraft's, PdfCraft's and CADCraft's builds have a `?host=parent` bridge, on which a page of their own origin opens a file in them and hears each save and whether there are unsaved changes. Serve the editor with the shim, lattice's page beside the build, and frame it from your portal:

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

The shim hears only your portal's origin and its own frame, and the build may then be framed by its own origin and your portal, and by nothing else. A portal reached at several addresses is several origins: give `portal=` each of them, as a list, and have the portal's frame add `?host=<its own origin>` to the shim's URL, which says which one frames it ([portalr ADR-0084](../../../portalr/adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md)); every origin is https, or http on loopback. Send `lattice:open` once the shim says `lattice:ready`. The app's talk level is `bridged`, level 1+: no commands reach the editor. A build with a JavaScript API takes `methods=`, those of it the portal may call by `lattice:call` `{ id, method, args }`, answered by `lattice:reply` ([ADR-0010](../adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)).

## Reading a revision

`files.read(ws, artifact_id, version=None, part="content")` returns the bytes of the head or of a version, or its `text` or `review`. It resolves the artifact through the workspace first, which asks `authorize` and answers a restricted artifact as a missing one, and only then reads the bytes the revision names.

## Collecting what nothing names

```python
deleted = await files.collect(system_ws)
```

Bytes are put before the revision that names them is committed, so a failure in between leaves bytes no revision names. `collect` deletes the workspace's blobs that no pending proposal and no revision of a native file, archived ones included, names, unless they were put within `keep`, a day by default (`NativeFiles(..., keep=)`). Putting bytes again marks them as put now, so bytes about to be committed are kept. Run it per workspace, as an actor that sees everything there: it refuses a handle from which anything is hidden, whose reads would leave out what a hidden revision names.
