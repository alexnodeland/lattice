# RFC-0003: Native files as artifacts

**Status:** Draft
**Author:** Alex Nodeland
**Created:** 2026-10-16
**Discussion:** [#248](https://github.com/alexnodeland/lattice/pull/248)
**Siblings:**

- [artifactr ADR-0003][a-adr-0003] fixes the two patch kinds and keeps types from defining their own. This RFC adds none, and leaves ADR-0003 as it is.
- [artifactr ADR-0004][a-adr-0004] makes every edit name its base version and writes an immutable revision. Native files keep both.
- [artifactr ADR-0034][a-adr-0034] is ports and adapters. The new package's app and blob ports follow it.
- [lattice RFC-0002](0002-portalr-the-portal.md) is portalr, which gains a renderer for native files and their page previews.
- [stackr ADR-0035][s-adr-0035] builds the thin images. The first app's worker is built the same way.

## Summary

A new package, `artifactr-craft`, gives artifactr artifact types for files in native formats: Word documents first, then presentations, spreadsheets, PDF, SVG, images, CAD and audio. An artifact of such a type is a small Pydantic manifest that points, by SHA-256, to the file's bytes in a blob store; the file is the source of truth, and nothing parses it into Pydantic fields. People edit in the app's browser build, hosted by the deployment; agents edit through the same app run headless in a sandbox, by batches of its own commands. Either way the new revision is an ordinary JSON Patch on the manifest whose first operation tests the old digest. Each type declares how concurrent writers are kept apart (`lock` by default, `rebase` where the app's commands name what they change by stable id), and what changed inside the file, such as a new comment, is read from it and recorded with the revision, so a comment can start an agent's turn. artifactr's core does not change, and lattice-core does not change. The pilot is one app, WordCraft, for `.docx`; a second app waits for the exit criteria in [Phases](#phases).

This changes artifactr's documentation, portalr and stackr as well as adding a package, so it is in lattice's series rather than artifactr's.

## Motivation

- **Work arrives as files.** The documents people and agents work on together are often a contract in `.docx`, a deck in `.pptx` or a model in `.xlsx`. artifactr's types hold JSON data and Markdown. An application today either converts the file to Markdown, losing styles, tables, comments and tracked changes, or keeps it outside artifactr, losing revisions, proposals, attribution and the log.
- **A model should edit the file, not a copy.** Converting `.docx` to Markdown and back is lossy in both directions. An app that reads and writes the format natively, and exposes its edits as commands, lets an agent change the real file.
- **The craft apps make it plausible.** [getartcraft.com/apps](https://getartcraft.com/apps) lists thirteen open-source Rust apps for native formats, each with a web build. One of them, [WordCraft](https://github.com/storytold/wordcraft), documents a headless MCP server that edits `.docx` by command. The [evidence](#evidence) records what was checked, and what was not.
- **The hard parts are artifactr's, not the app's.** Bytes that don't fit in the log, a write path that can't run an app inside a transaction, a sandbox for user files, and previews in portalr all need deciding once, before any second format repeats them differently.

## Design

### Overview

```mermaid
graph LR
    person["a person, in the app's<br/>browser build (own origin)"] -- "bytes on save" --> portal
    agent["agent tools<br/>(edit_native, view_page, ...)"] --> craft["artifactr_craft"]
    portal["portalr<br/>(the bridge: lease, save,<br/>preview, history)"] --> router["craft_router"]
    router --> craft
    craft -- "1. source bytes,<br/>command batch" --> worker["craft worker<br/>(sandboxed, no network)"]
    worker -- "2. new bytes,<br/>outline, text" --> craft
    craft -- "3. put by digest" --> blobs[("Blobs<br/>tenant, workspace,<br/>artifact, sha256")]
    craft -- "4. EditArtifact:<br/>test old digest,<br/>replace content" --> ws["Workspace.commit"]
    ws --> log[("artifactr's log<br/>and revisions")]
```

For an agent's edit:

1. The package loads the artifact's current manifest and its bytes.
2. It sends the bytes and a batch of commands to the app's worker, which returns the new bytes, a bounded outline, the plain text, and the comments and tracked changes.
3. It puts the new bytes, the batch and the text into the blob store, each under its digest.
4. It commits an `EditArtifact` through the one write path ([ADR-0002][a-adr-0002]). The patch tests the digest it started from, then replaces the content and the outline.

If anything fails before step 4, nothing is committed, and what step 3 wrote is collected as unreferenced. A person's save skips step 2's commands: the worker only reads the bytes the browser saved, and steps 3 and 4 are the same.

### The package

```text
packages/artifactr-craft/
├── pyproject.toml           distribution artifactr-craft, import artifactr_craft
├── src/artifactr_craft/
│   ├── types.py             NativeFile, Blob, Provenance, and WordDocument
│   ├── blobs/               the Blobs port, InMemoryBlobs; sql/ behind the [sql] extra
│   ├── apps/                the CraftApp port, FakeApp, and wordcraft/ (the adapter)
│   ├── agent.py             NativeFileTools, a pydantic-ai toolset
│   ├── fastapi.py           craft_router, behind the [fastapi] extra
│   └── worker/              the job runner the worker image runs
├── schemas/                 artifactr-craft.v1.json and the router's OpenAPI document, with drift tests
└── tests/                   including test_layering.py and corpus/
```

- **A separate distribution,** released by release-please on its own version, as every package of lattice is. Applications that don't edit native files install nothing new.
- **It depends inward only.** It imports artifactr's public API, the names in `__all__`, and `lattice_core.sql`'s tenancy helpers; artifactr imports nothing of it. Its `tests/test_layering.py` holds it there, as relayr's does.
- **It lives in the monorepo.** CI runs every affected project and its dependents (lattice ADR-0002), so a change to artifactr runs this package's tests too. That is most of the compatibility story: the plugin cannot drift from the core unnoticed. Its `artifactr-ai` requirement is a lower bound, raised by hand, with an upper bound below artifactr's next minor version until artifactr reaches 1.0.

### Artifact shape

```python
class Blob(BaseModel):
    """Bytes in the blob store, named by their digest."""
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    size: int = Field(ge=0)
    media_type: str


class Change(BaseModel):
    """One thing that changed inside the file, read from both versions."""
    kind: str                     # "comment_added", "change_tracked", "slide_added", ...
    ref: str | None = None        # a stable id in the file, such as a comment's
    text: str = Field("", max_length=500)
    anchor: str = Field("", max_length=200)
    author: str | None = None     # as the file says: shown, never trusted


class Provenance(BaseModel):
    """How a revision's content was made. Who made it is the revision's actor."""
    source: Literal["upload", "save", "commands", "sync"]
    app: str | None = None        # "wordcraft"
    app_version: str | None = None
    build: str | None = None      # the worker image's or the web build's digest
    base: str | None = None       # the sha256 it was made from; None for a new file
    commands: Blob | None = None  # the batch, as canonical JSON, when there is one
    changes: tuple[Change, ...] = Field((), max_length=50)
    via: str | None = None        # the device, for a revision from the sync bridge


class NativeFile(Artifact, abstract=True):
    formats: ClassVar[frozenset[str]]                  # the media types the type accepts
    merge: ClassVar[Literal["lock", "rebase"]] = "lock"
    write_policy: ClassVar[WritePolicy] = "propose"

    name: str                                   # the file name people see
    content: Blob
    text: Blob | None = None                    # the plain text, for diffs and search
    review: Blob | None = None                  # comments and tracked changes, as JSON
    outline: str = Field("", max_length=4_000)  # what the agent sees
    pages: int | None = None
    provenance: Provenance

    def render_for_agent(self) -> str:
        return f"{self.name} ({self.pages} pages)\n{self.outline}"


class WordDocument(NativeFile):  # registered as "word_document"
    formats = frozenset({DOCX})
```

- **The file is the source of truth.** The manifest holds what artifactr needs to version, show and route it, and the outline and text are derived from the file by the app when the revision is made. Nothing is parsed into Pydantic fields, so nothing is lost in a model the format doesn't fit.
- **Bytes never enter the log.** `ArtifactCreated` and `ArtifactChanged` carry the data, every revision stores the resulting data ([ADR-0004][a-adr-0004]), every WebSocket replay sends the log, and relayr bridges both events into reflexr with their data. A manifest is a few kilobytes; a `.docx` is often megabytes. Every byte in the manifest is paid per revision and per bridged event, which is why the outline is bounded and the full text is a blob.
- **`render_for_agent` is synchronous and does no IO.** The agent can't call the app when it reads an artifact, so what it sees by default is the outline the app wrote when the revision was made. Deeper reads are the toolset's (see [What the agent sees](#what-the-agent-sees)).
- **The command batch is provenance, not the change.** It is stored as its own blob and named by `provenance.commands`, so a revision says how it was made, a batch can be replayed onto a newer head where the type allows it ([Merge strategies](#merge-strategies)), and the manifest stays small.
- **Write policy defaults to `propose`.** A change to a binary is harder to check by eye than a JSON diff, and an app in alpha may lose formatting. An application can choose `direct`.

### Edits: no third patch kind

The question was whether a "command batch" should become a third patch kind beside JSON Patch and anchored text edits. It should not, and ADR-0003 needs no change.

- **Core can't apply it.** `core.commit` is pure ([ADR-0001][a-adr-0001]): `apply_patch(data, patch)` must return the resulting data. A command batch's result exists only after a native app has run, which is IO, takes seconds, and depends on the app's version. It can't happen inside `commit`, and it must not happen inside the storage transaction either, which holds the workspace's row lock ([ADR-0021][a-adr-0021]).

A whole-file replace is already expressible. The revision is a JSON Patch on the manifest, which the package builds, never `Versioned.edit`'s diff:

```json
[
  {"op": "test",    "path": "/content/sha256", "value": "<the digest the batch ran on>"},
  {"op": "replace", "path": "/content",        "value": {"sha256": "...", "size": 48213, "media_type": "..."}},
  {"op": "replace", "path": "/text",           "value": {"sha256": "...", "size": 9120,  "media_type": "text/plain"}},
  {"op": "replace", "path": "/outline",        "value": "..."},
  {"op": "replace", "path": "/pages",          "value": 3},
  {"op": "replace", "path": "/provenance",     "value": {"source": "commands", "app": "wordcraft", "base": "...", "commands": {...}, "changes": [...]}}
]
```

The `test` operation is what makes a binary safe under artifactr's rules: a proposal accepted later is applied to the head as it is then (`core.respond` rebases by applying), and without the test a stale replace would silently discard everything committed in between. With it, the accept fails as `PatchFailed` ("… is not equal to tested value …"), checked in the [evidence](#evidence).

- **Summaries come from the batch.** The package passes `summary=` on the command, written by the agent or from the batch, so change notes don't read `test /content/sha256; replace /content; …`. The type's `describe_change` covers commits that don't.
- **What this records instead:** an artifactr ADR, "native files are manifests over JSON Patch", which confirms ADR-0003 and adds a section to the artifact types guide.

### Merge strategies

Binary files don't merge, and artifactr doesn't need them to. Each native type declares, in `merge`, how concurrent writers are kept apart, chosen from what its app can do:

| Strategy | How | For | WordCraft |
|---|---|---|---|
| `lock` (the default) | One writer at a time, through a renewable lease. Anyone else's change becomes a proposal | Every app; the only choice where commands don't name their targets by stable id: images, audio, CAD, video, and today's documents | Yes |
| `rebase` | Command batches that name what they change by stable id, ordered by the server. A stale batch is refused with `VersionConflict`, and its author replays it on the new head | Apps whose commands are anchored to ids | No: its commands act on positions and the selection |
| `crdt` | The app's own CRDT updates, stored with revisions | Only an app whose document model is a CRDT | Reserved: no craft app has one |

**Lock.** The lease is artifactr's own: `Storage.acquire_lease(scope, "artifactr-craft:edit:<artifact>", holder, ttl)`, the mechanism thread claims use ([ADR-0019][a-adr-0019]), so it needs no core change. It lasts 60 seconds and is renewed every 20: by the portal page while a person has the file open, and by the toolset for the length of an agent's edit.

- **The holder commits directly,** subject to the write policy. Anyone else gets their change recorded as a proposal (`ProposeChange`), which the holder sees when they finish. Nothing waits on the lock, which was ADR-0004's objection to locks: an agent doesn't hold one across model calls, and doesn't wait for one either. It proposes and moves on.
- **The lock is advisory.** Core doesn't know about it, so `edit_artifact` over REST or MCP isn't stopped. The `test` keeps such a write from being silent: either it fails, or the holder's next save does.
- **A person's stale save is never discarded.** If their lease lapsed and someone committed meanwhile, the `test` fails, and the package records their bytes as a proposal against the head, saying which version they were saved over. The reviewer sees both versions' pages and chooses. Rejecting and replaying is not available for a person, because their edit is bytes, not commands.
- **An agent's stale edit is refused,** and the agent plans again against the new head, with the summaries of what changed ([ADR-0008][a-adr-0008]), as ADR-0004 expects.

**Rebase** needs commands that say what they change by stable id, so that a batch means the same thing on a newer head. The server orders everything already: every workspace's log is numbered without gaps ([ADR-0005][a-adr-0005]), and every edit names its base version. WordCraft doesn't qualify. A position is a story, a path of block indexes and a byte offset; paragraphs, tables and cells have no ids; and accepting a tracked change or resolving a comment acts on the selection. Comments (a durable id) and bookmarks (a name) are its only stable handles. `select_text` anchors by content, as artifactr's text edits do, but a rule built on it would be a heuristic, so WordCraft stays `lock`. `rebase` waits for an app whose model has ids.

**Why not CRDTs.** A CRDT lets replicas edit without coordinating and still converge. lattice has the coordinator a CRDT exists to do without:

- **A server orders every write.** It is always there, because agents run on it, and it numbers each workspace's events (ADR-0005). Ordered operations with optimistic checks give the same convergence with no merge function.
- **Collaboration is turn-based by design** (ADR-0004). Revisions, proposals and write policies ([ADR-0009][a-adr-0009]) are discrete, attributed, reviewable changes. A CRDT's keystroke-level stream would have to be cut back into exactly those.
- **Convergence is not validity.** A merged document must still be a valid file, with consistent numbering, comment anchors and tracked-change ids, and a CRDT promises only that replicas agree.
- **No craft app has a CRDT model.** No CRDT or OT library is in any of the thirteen apps' lock files. Mapping `.docx` onto Yjs, Automerge or Loro and back is the lossy conversion D1 rejects. FigCraft, the one app with collaboration, chose server-ordered last-writer-wins over property-level change sets: central ordering again.

That flips if an app ships its own CRDT model that its files round-trip; if people must edit offline, on several devices, for hours; or if several people must type in one document at once and a lock with proposals isn't good enough. `crdt` would then store the app's updates. A blob of updates per revision needs no core change; a new patch kind would change ADR-0003. That choice waits for the app.

**Proposals on native files.** A proposal accepted after the head has moved fails the `test` as `PatchFailed`. Where the type is `rebase`, portalr offers to replay the proposal onto the current version, which makes a new proposal from the same batch. Where it is `lock`, the reviewer sees both versions' pages and accepts one. Accepting with changes (`RespondToProposal.changes`) isn't offered for native kinds; edits after accepting are a new revision.

### Blob storage

```python
class Blobs(Protocol):
    async def put(self, scope: Scope, artifact_id: ArtifactId, data: bytes, media_type: str) -> Blob: ...
    async def get(self, scope: Scope, artifact_id: ArtifactId, sha256: str) -> bytes | None: ...
    async def collect(self, scope: Scope, referenced: Set[tuple[ArtifactId, str]], *, older_than: datetime) -> int: ...
```

| Decision | Choice | Why |
|---|---|---|
| Where the port lives | In `artifactr_craft`, not in artifactr's `Storage` | Adding methods to `Storage` breaks every storage an application wrote itself, and nothing else in artifactr needs bytes yet. If a second package needs attachments, the port moves into artifactr then, unchanged |
| Key | `(tenant, workspace, artifact, sha256)` | Matches ADR-0021's keys, which start with the tenant and the workspace. Keying by artifact makes a blob's access the artifact's access: a manifest that names another artifact's digest finds nothing, so a restricted artifact's bytes ([ADR-0062][a-adr-0062]) can't be read through another artifact |
| Deduplication | Within one artifact only | Its revisions share unchanged bytes, and a revert costs nothing. Across tenants, deduplication would tell an uploader that someone else already has a file |
| Order of writes | Put first, by digest, idempotent; then commit | No transaction spans the two. Blobs are immutable, so a put that is never committed is only garbage, and a commit never names bytes that aren't there |
| SQL | `artifactr_craft_blobs`, `bytea` (SQLite `BLOB`), storage `EXTERNAL` so PostgreSQL doesn't try to compress zipped formats; the package's own Alembic scripts and version table, as artifactr's ([ADR-0021][a-adr-0021]) | One database, no new service |
| Tenancy | `TenantSession` and `tenant_policy` from `lattice_core.sql.tenancy`, as artifactr's adapter uses them ([ADR-0066][a-adr-0066]) | Row-level security under the scoping, with no change to lattice-core |
| In memory | `InMemoryBlobs`, a dict by key | For tests and examples |
| Size | 25 MiB per blob by default, configurable up to 100 MiB on PostgreSQL; the router refuses larger bodies before reading them | `bytea` values are read whole into memory. A larger limit needs streaming and an object store |
| Object store | Deferred | An S3-compatible adapter is the same port; it needs a service in stackr and isolation by key prefix instead of row-level security. It waits for a deployment that hits the size limit |
| Retention | Follows artifactr's revisions | Revisions are append-only, so every blob a revision names is kept. `collect` deletes what no revision and no pending proposal names, and was put more than a grace period ago (one day by default), so an upload in flight survives. Deleting a tenant deletes its rows |
| Referential integrity | Checked on read, not on write | Every surface can commit `edit_artifact` ([ADR-0002][a-adr-0002]), and core can't look in the blob store, so a hand-made patch can name a digest that isn't there. Reads then show "content unavailable", and the tools refuse to edit it until the content is replaced. No one gains access by it, because of the key |

Renders (page images) are a cache, not blobs: keyed by the content digest, the page, the scale and the worker image's digest, and evicted by age. The spike found WordCraft's renders byte-identical across processes, and fonts are the only input from the host: it uses system fonts when they are installed. The worker image installs none, so its renders depend on the image alone, and a cache miss only costs time.

### The app port

```python
class CraftApp(Protocol):
    name: str
    async def apply(self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float) -> Applied: ...
    async def inspect(self, source: bytes, *, deadline: float) -> Inspection: ...   # outline, text, pages
    async def render(self, source: bytes, page: int, *, dpi: int, deadline: float) -> bytes: ...  # PNG
    async def commands(self) -> Sequence[CommandSpec]: ...   # the app's catalog, for the agent
```

Each call is stateless: bytes in, bytes out. A document is never held open between calls, so no state carries from one tenant's file to another's, and a crash loses one call.

| Transport | Assessment |
|---|---|
| **MCP over stdio (chosen)** | WordCraft's headless surface, `wordcraft-cli mcp`, which speaks only stdio: 16 tools, of which the pilot uses `open_document`, `new_document`, `batch`, `select_text`, `get_text`, `inspect_document`, `render_page`, `save_document` and `list_commands`. Its `--automation-read-root` and `--automation-write-root` confine what it may read and write to two directories. stdio needs no listening port at all, which is what makes a no-network sandbox possible. The MCP Python SDK is already a dependency of `artifactr[mcp]` |
| The JSON control channel (`--control <port>`) | Bound to 127.0.0.1, with a key from a file, newline-delimited JSON. It belongs to the desktop app, not the CLI, and would need a listener and a key inside the sandbox for nothing stdio lacks |
| One CLI call per operation | No batches and no inspection, and output parsed from a terminal |
| Linking the Rust crates | A Python extension built from young crates, inside the application's process: no isolation from a hostile file, and a Rust toolchain in every build |

Two adapters implement the port for each app:

- **`Subprocess`** spawns the app's CLI per call, over stdio, with a deadline and a kill. It is for tests and development, on trusted files, and its documentation says it is not a sandbox.
- **`Worker`** sends the call to a worker container, below.

### The sandbox

Opening a user's `.docx` runs a young parser on hostile input: a zip bomb, XML nested a million deep, a 40,000-pixel image, a link to a remote template. Rust's memory safety removes one class of bug, not panics, runaway allocation or slow paths. The worker treats every file as hostile.

- **A worker per app, in stackr's compose,** on an internal network (`internal: true`) that only the application joins: no route out, no published port. The application reaches it by service name. Nothing listens on the host; a developer who wants to call it from outside the stack goes through the application.
- **One process per call, in a long-lived container.** The worker's runner, a small program in `artifactr_craft.worker`, accepts one job on the internal network, spawns the app's CLI over stdio in a fresh temporary directory given as its read and write roots, and returns its result. It never runs two jobs in one process. Starting the CLI took about 4 ms in the spike, against 0.4 to 8 s to start a container, which is why the container lives on and the process doesn't.
- **Limits on every call:** a wall-clock deadline (30 s for an edit, 10 s for a render by default), CPU time, address space and file size by `setrlimit`, a cap on the size of what comes back. A breach kills the process and is a typed failure: `timeout`, `crashed`, `too_large`, `refused`.
- **The container:** non-root, read-only root file system, a size-limited `tmpfs`, all capabilities dropped, `no-new-privileges`, the runtime's default seccomp profile, and memory, CPU and PID limits. These are compose settings, so the template, the single host and the AWS stack carry them the same way.
- **stackr owns the policy,** because it owns the network, the limits and the image. The package documents what it needs and ships the runner; it doesn't choose the limits for a deployment.
- **Tested with hostile files.** The phase that adds the worker adds a corpus of hostile inputs, and a test that each one ends in a typed failure within its deadline, and a test from inside the worker that a connection out fails.

### What the agent sees

| Need | Tool or hook | Budget |
|---|---|---|
| What the file is | `render_for_agent`: name, pages and the outline the app wrote at the revision | The outline's 4,000 characters, which is the capability's `max_render_chars` |
| Its words | `read_native(artifact_id, pages)`: the text blob, cut to the pages asked for | 8,000 characters a call, with how much remains |
| Its comments and tracked changes | `read_review(artifact_id)`: the `review` blob, with each comment's id | 50 items a call |
| Its look | `view_page(artifact_id, page)`: one rendered page, as an image, for models that take images | One page a call, at a fixed resolution; off unless the application turns it on |
| What it can do | `find_commands(query)`: the app's commands that match, through its `list_commands` | Ten a call; the full catalog (617 commands in WordCraft 0.7.0) is never in the prompt |
| To change it | `edit_native(artifact_id, base_version, commands, summary)` | One batch a call; returns `Applied`, `Proposed`, or the conflict |
| To start one | `create_native(kind, name)` | |

WordCraft describes each command's parameters as a free-text signature, such as `{"rows": n, "cols": n, "style"?: string}`, not as JSON Schema, so neither the model nor the package can validate a batch before the app runs it. A refused command comes back as the tool's error, and the batch commits nothing.

The toolset is `NativeFileTools`, registered on the agent beside the application's own, as [ADR-0017][a-adr-0017] has it. External agents over MCP get the same tools on artifactr's MCP server. Everything they read is artifact-scoped, so authorization is artifactr's: the tools open workspaces through `Workspaces`, whose `authorize` hook grantr answers.

### Discovery and compatibility

- **Explicit, as types already are.** A type registers when its class is defined, and `Workspaces(storage, types=[...])` is an allowlist ([ADR-0019][a-adr-0019]). An application imports `WordDocument`, lists it, and gives the toolset a `CraftApp`. Nothing is activated by being installed.
- **No entry points.** A `artifactr.types` entry-point group would load code because a package is on the path, which is a supply-chain door with no benefit: the application still has to list the type.
- **Compatibility** is the monorepo's CI and the lower bound above, and the layering test that imports only `__all__` names.

### People edit in the browser

People edit in the craft app's web build, served by the deployment, so nothing is installed. Agents still edit on the server, through the worker.

**What the web build is today.** For WordCraft 0.7.0, verified:

- **A standalone UI.** It exports no JavaScript API and listens for no `postMessage`. Files come in through a picker, drag and drop or paste, and go out through `showSaveFilePicker` or a download. The control channel has nothing in the browser to replace it, and there is no AutoSave and no recovery.
- **Its hosting needs are modest.** It is 40 MB of WebAssembly, 15 MB gzipped (its `HOSTING.md` says 13 and 5). It needs no COOP or COEP and runs no workers. Its CSP must allow `wasm-unsafe-eval` and one inline module script. It calls no remote host.
- **It runs the CLI's engine.** The web build and the CLI depend on the same engine crates, so a file saved in the browser and one written by the worker come from the same code at the same release. Only fonts differ between the two, and fonts change renders, not the `.docx`.

So the pilot needs an embedding API that doesn't exist yet:

| Option | What | Assessment |
|---|---|---|
| **A. An embedding API upstream (recommended)** | A small `postMessage` protocol in the web build: open bytes with a name, save to bytes, report dirty and idle, a read-only mode | Least for us to own, and useful to upstream; depends on upstream taking it |
| B. Our own shell over the upstream crates | A crate that depends on WordCraft's engine and UI crates by git, pinned by commit, adding that API, built in CI | Works without upstream, but makes us maintain a WebAssembly build that tracks an alpha |
| **C. Check out and check in (works today)** | portalr takes the lease and downloads the revision, and opens the hosted app in a new tab. The person saves to disk and uploads, which commits the revision and releases the lease | Clunky, but needs nothing from upstream |

The pilot ships C, which proves the hosting, the lease and save-to-revision, and proposes A upstream at the same time. B is built only if A is refused and the pilot shows embedding is worth a build of our own.

With an embedding API, the editor is an iframe:

- **On an origin of its own.** stackr serves the release's files, pinned by version and checksum, from a host name of their own, never portalr's. An iframe with `allow-scripts allow-same-origin` is a sandbox only when its origin differs from the page's, and only that origin needs `wasm-unsafe-eval`; portalr's CSP gains only a `frame-src` naming it.
- **Sandboxed and unframeable elsewhere.** The iframe gets `sandbox="allow-scripts allow-same-origin allow-downloads"`. The editor's origin sends `frame-ancestors` naming the portal and a CSP of `default-src 'self'`, plus the inline script's hash and `wasm-unsafe-eval`.
- **The portal page is the bridge.** It fetches the revision through `craft_router`, under artifactr's read check, and posts the bytes into the iframe. It takes the lease and renews it while the editor is open. On save it sends the bytes to `craft_router`, which commits a revision as the person, with `source: "save"`. Messages are checked by origin in both directions. The iframe holds no token and calls no API, so tenant scoping stays in the portal page and on the server.
- **No keystrokes reach the server.** A revision is made on save and on close, and after a minute idle with unsaved changes once the app reports idle.
- **Hostile files now also open in the browser,** inside the person's own browser sandbox, which is what it is for. That doesn't replace the worker: the server still opens every revision to read its outline, text, comments and changes.

Embedding is not added to portalr's bundle. It loads only when a person opens a native file, from the editor's origin, with no extra weight for anyone else.

### Events and user-side edits

artifactr records revisions, never keystrokes. How finely a person's work becomes revisions depends on what the app reports:

| Level | What reaches lattice | What it needs from the app | WordCraft 0.7.0 |
|---|---|---|---|
| 1. Save | Bytes, when the person saves | Nothing | Yes, in the browser and on the desktop |
| 2. File watch | Bytes, once a file in a synced folder settles | Saves that never leave a half-written file | Desktop saves write a temporary file and rename it |
| 3. Commands | Bytes, with the commands that made them | A command journal or stream | No stream. A macro can be recorded and read back over the desktop control channel, by polling. GridCraft has `engine.journal` |
| 4. Presence | Who has the file open, and where | Events the app pushes | None: both surfaces only answer requests |

Level 1 is the pilot's. Level 2 is the desktop phase's. Level 3 only attaches the commands to a revision that is still made on save, as its `provenance.commands`; it never puts one event per command in the log. Level 4 is live state, not history. It would need an app that pushes events, and a live channel for artifacts, which artifactr doesn't have, so it waits.

**Provenance on every revision.**

| Question | Where the answer is |
|---|---|
| Who | The revision's actor, as artifactr records it (`user`, `agent`, `external_agent`, `system`), never the name in the file |
| How | `provenance.source`: `upload`, `save`, `commands` or `sync`. A check-in under the person's lease is a `save`, though its bytes arrive by upload; `upload` is a new file, or a replacement made without the lease |
| Made from | The previous version, and `provenance.base`, the digest of the content it was made from |
| What | `content.sha256` |
| By which build | `provenance.app`, `app_version` and `build` |

**What changed inside the file.** For every revision, the worker reads the new bytes' comments, tracked changes and outline, and stores them as the `review` blob. It then compares them with the previous revision's and writes what changed into `provenance.changes`:

- a comment added, replied to, resolved or deleted, keyed by its durable id;
- a tracked change made, accepted or rejected;
- pages added or removed;
- for later formats, their own kinds, such as a slide added.

There are at most 50 changes, and each text is cut to 500 characters. They travel in the revision's patch, so change notes, relayr's bridged `artifact_changed` and its reflexr rules, and portalr's history see them with no new event type. The spike found `inspect_document` gives only counts and indexes, while `review.comments` and `review.changes` give the author, date, anchor, text and id, so the worker reads those.

**A comment can start a turn.** Suppose a person's save, or a synced file, adds a comment that addresses the agent by the handle the application configures, such as `@agent`. The package then posts a message in the artifact's thread, as that person, quoting the comment, its anchor and its id. The agent answers in the file with `review.reply`. Comment ids are stable, so the reply is anchored even under `lock`. While the person holds the lease, the reply is a proposal.

The guardrails:

- **Only new comments start a turn:** ones the previous revision didn't have.
- **Never from an upload.** A received file's comments are someone else's words.
- **The file's author field is shown, never trusted.** The message is attributed to the person whose save added the comment.
- **The comment reaches the model as untrusted text,** as that person's message, like anything else they type.

**The desktop sync bridge** comes in a later phase. It is a separate adapter: a small program on the person's machine that watches a folder, waits for a file to settle after its rename, and commits the revision as the person, with their grantr token, with `source: "sync"` and `via` naming the device. It is not an actor of its own, because the edit is the person's and a bridge actor would hide who made it.

The spike found two hazards:

- **WordCraft doesn't notice a file changed on disk.**
- **Its desktop AutoSave is on by default,** so it would silently overwrite anything the bridge wrote into a file the person has open.

So the bridge never writes into a watched file. An agent's revision reaches the person as a proposal, or as a file beside theirs.

### The log, feedback and telemetry

- **No new events.** A native edit, whoever makes it, is an `artifact_changed` like any other, with the manifest patch, its summary and the trace it was committed in ([ADR-0033][a-adr-0033]). relayr bridges it unchanged, so a reflexr rule can react to a Word document changing, and sees the manifest, never the bytes.
- **Feedback** targets an artifact version, as it does today ([ADR-0028][a-adr-0028], [ADR-0038][a-adr-0038]). A score on a revision of a native file attaches to the trace that made it.
- **Spans** for `apply`, `inspect` and `render`, children of the tool call or request, with the app, its version, the image digest, the command count, the bytes in and out and the outcome. Digests, never content: a document's text never reaches a span.
- **Metrics:** a duration histogram per operation and a count of failures by kind, through the same SDK views as artifactr's metrics ([ADR-0036][a-adr-0036]), with the tenant attribute artifactr uses, so portalr's per-tenant readers see them.

### portalr

- **A renderer for native files** in `ui`'s registry: a page strip of previews, the file's name and size, a download link, and the outline. Its `text(data)` is the outline, so revision diffs work before any preview loads; the full text diff reads the text blob.
- **Revision history** is artifactr's revisions, as for every kind. A diff between two revisions shows the changed text and, side by side, the pages whose renders differ.
- **Routes in `craft_router`,** mounted by the application beside artifactr's, with the same `resolve_actor` and authorization: upload a file as a new artifact or a new revision, download a revision's content, and fetch a revision's page. Every route names the artifact and the revision, never a bare digest, so the check is artifactr's read or edit of that artifact.
- **Editing** opens the app's browser build, as [People edit in the browser](#people-edit-in-the-browser) describes: check-out and check-in first, then an embedded editor.
- **Conflicts and proposals:** a stale save shown as a proposal with both versions' pages, and the lease's holder shown on the artifact while it is held.

### stackr

- **A recipe, not a default.** The template gains a `native_files` question, off by default. On, it adds the worker service, its internal network and its limits, wires `Worker` into the application, and serves the app's browser build.
- **The browser build is static files on a host name of their own,** served by the stack's edge (Caddy on the single host), from the release's `wordcraft-web` archive, checked against `SHA256SUMS.txt` and pinned to the same version as the worker. The files keep their hashed names and their SRI, and are cached for a long time. The headers are a CSP for that origin alone, `frame-ancestors` naming the portal, and `application/wasm`. Nothing calls out.
- **The image is stackr's thin image.** WordCraft publishes no image the spike could find, and its Linux CLI comes only inside the full app's tarball. stackr builds an image from that tarball's `wordcraft-cli`, checked against the release's `SHA256SUMS.txt`, in the way and with the provenance of [ADR-0035][s-adr-0035], pinned by version and digest. The CLI needs only the C library, so the image is a slim base, the CLI, the runner and no fonts. Upstream signs nothing and publishes no SBOM, so the checksum is the whole chain of custody from upstream, and stackr's attestation starts at its own build.
- **Notices.** The image carries the app's licence files and a `NOTICE` naming its source and version, and the template's licence notes list it. A recipe is added only for an app whose licence is verified.

### Fidelity and what "supported" means

A format is supported when its corpus round-trips through the app without loss in the features its row claims, and when edits do what they say.

- **The corpus** lives in `tests/corpus/<format>/`: files generated by our own scripts, each covering one feature, plus a few public-domain or permissively licensed real documents with their provenance recorded.
- **Loss is measured on the format, not the bytes.** For `.docx`, open and save with no edits, then compare the normalized OOXML of the input and the output, feature by feature: text, paragraph styles, run properties, tables, lists, images, headers and footers, footnotes, comments, tracked changes, section properties. Each feature is preserved, changed or dropped.
- **Saving twice is a fixpoint:** saving what was saved changes nothing, after normalization.
- **A feature matrix per format,** published in the package's docs from the nightly run: supported, changed on save, or dropped. "Supported" is per feature, never per format.
- **Determinism decides what is compared.** The spike found WordCraft's `.docx` output identical across runs except `docProps/core.xml`, where every save stamps the clock as `dcterms:modified`, adds one to `cp:revision` and writes `--author` as `lastModifiedBy`, with no way to fix the clock. Tests therefore compare with `core.xml` normalized. The package passes the acting participant's name as `--author`, so the file records who made a revision as artifactr does, and accepts that saves of unchanged content make new blobs.
- **Where it runs:** the fake app on every pull request; the real worker image in the Acceptance job and nightly, since it needs a container runtime and the release binary.

### What changes in each package

| Package | Changes | Breaking |
|---|---|---|
| artifactr | An ADR and a section of the artifact types guide: native files are manifests over JSON Patch, with a `test` on the content digest | No |
| artifactr-craft | New | |
| portalr | The native file renderer in `ui`; previews, the revision page diff, check-out and check-in, and later the embedded editor and its bridge, in `app` | No |
| stackr | The `native_files` question; the worker service and network; the worker's thin image; the browser build on its own origin | No |
| lattice-core | Nothing | |

### Phases

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0. Spike | This RFC's [evidence](#evidence) | Done |
| 1. The package | `NativeFile`, `Blob`, `Provenance`; the `Blobs` port with in-memory and SQL adapters, migrations and row-level security; the `CraftApp` port and `FakeApp`; the edit lease | 100% coverage; the blob contract suite passes on memory, SQLite and PostgreSQL; a two-tenant test reads nothing across tenants; `collect` keeps every referenced blob, pending proposals' included |
| 2. WordCraft, headless | The `Subprocess` adapter over stdio MCP; outline, text and `review` at every revision; the `.docx` corpus and the fidelity report | The report runs nightly, and the feature matrix is published |
| 3. The worker and the agent | The runner, stackr's image and recipe, the hostile corpus; `NativeFileTools`; `lock`, with an agent's work as proposals while a person holds the lease | Every hostile file ends in a typed failure within its deadline; egress from the worker fails; scripted-model tests (`FunctionModel`) for an edit, a proposal and a conflict |
| 4. The browser pilot | The browser build on its own origin; portalr's renderer, previews, page diffs, and check-out and check-in under the lease; a stale save kept as a proposal; the embedding API proposed upstream | Each `bdd` scenario passes, a stale save included; the editor's origin serves nothing that calls out |
| 5. Events | `provenance.changes`; a comment that addresses the agent starts a turn, answered by `review.reply`; the embedded editor, if phase 4 got an embedding API | A person's comment, saved in the browser, gets the agent's reply in the file as a proposal, in a `bdd` scenario |
| 6. The desktop bridge | The sync adapter, with its own design note first | A file saved on the desktop becomes a revision within its settle time, and an agent's revision never lands in an open file |
| 7. Docs and ADRs | The package's site section, its guide, the ADRs this RFC leads to | The section builds |

Phases 3 and 4 depend only on 2, and can run side by side.

**Before a second app:**

- WordCraft's feature matrix has held across two of its releases, with no feature moving from supported to dropped.
- No hostile input has escaped its limits.
- The second app's licence is verified from its repository, and it has a headless surface with the four operations of `CraftApp`, tagged releases with Linux binaries, and checksums.
- Its merge strategy is declared from what its commands are shown to address, not from its documentation.
- Its adapter needs no change to `CraftApp`, `Blobs` or `NativeFile`. If it does, the port was WordCraft-shaped, and is fixed before the app is added.

## Decisions

Recommended, for the maintainer to decide.

| # | Question | Recommended | Instead of |
|---|---|---|---|
| D1 | Artifact shape | A small manifest and content-addressed blobs; the file is the source of truth | Parsing the file into Pydantic fields; bytes inline in the data |
| D2 | Edits | JSON Patch on the manifest, testing the old digest; the command batch as a provenance blob. ADR-0003 unchanged | A third patch kind, "command batch", which pure core can't apply |
| D3 | Blob storage | A `Blobs` port in the package, keyed by tenant, workspace, artifact and digest; PostgreSQL `bytea` with a 25 MiB default limit; put first, collect what is unreferenced | Methods on artifactr's `Storage`; an object store first; deduplication across artifacts or tenants |
| D4 | Merge | A strategy each type declares: `lock` by default, through artifactr's leases, with others' work as proposals; `rebase` only for apps whose commands name stable ids; `crdt` reserved for an app whose own model is one | A CRDT library chosen by lattice, with `.docx` converted to it; last write wins; merging binaries |
| D5 | The app port | Stateless calls over MCP on stdio, one process per call; an adapter per app | The control channel's TCP port; one adapter for every app (their protocols differ); the CLI per operation; linking the crates |
| D6 | The sandbox | A worker per app on an internal network, with no published port and no egress, under rlimits and container limits; stackr owns the policy | The app's CLI in the application's own container; a long-lived app server shared by tenants |
| D7 | Agent perception | A bounded outline in the manifest; text, review, pages and the command catalog through tools | Calling the app from `render_for_agent`; the whole catalog in the prompt |
| D8 | Discovery | Explicit: import the type, list it, give the toolset an app | An entry-point group |
| D9 | The log and telemetry | No new events; spans and metrics on the package's own calls, digests only | New event types for native edits |
| D10 | People's editing | Browser first: check-out and check-in in the pilot, then an embedded editor through an embedding API proposed upstream; a desktop bridge later | Desktop and a bridge first; building our own shell over the crates before asking upstream |
| D11 | The browser editor's security | Its own origin, a sandboxed iframe, origin-checked messages; the portal page holds the token and the lease | Serving it from portalr's origin, with `wasm-unsafe-eval` in portalr's CSP |
| D12 | User-side events | Revisions on save, never keystrokes; provenance on every revision; changes read from the file and carried in the patch | Keystroke or command events in the log; new event types for comments; trusting the file's author names |
| D13 | Comments | A new comment that addresses the agent, saved by a person, starts a turn as that person's message; never from an upload | Every comment starts a turn; comments ignored |
| D14 | The desktop bridge | An adapter that commits as the person, with the device in the provenance; never writes into a watched file | A bridge actor of its own; writing agents' revisions into the person's open file |
| D15 | stackr | An opt-in recipe; a thin image and the browser build from one release, checked against its checksums, pinned by digest, with their notices | A worker in every generated application; upstream artifacts unpinned |
| D16 | Fidelity | A corpus, measured on normalized parts, and a feature matrix per format | Byte comparison; "supported" for a format as a whole |
| D17 | Scope | WordCraft only until the exit criteria hold | Several apps at once |

## Drawbacks

- **A young dependency on the critical path.** WordCraft's repository is nine days old, with six releases in seven days, and calls itself alpha. Its own documents disagree on how many commands it has (422, "over 270", and 617 in the binary). Its commands, tools and output can change in any release, and the adapter has to follow.
- **Two stores to keep consistent.** The manifest is transactional and the bytes are not; put-first and collection make the gap safe, not absent, and a hand-made patch can still name missing content.
- **One writer at a time.** Under `lock`, a second person or the agent proposes rather than edits while someone has the file open. Collaboration stays turn-based, as ADR-0004 chose, but the turns are coarser than in a Markdown document.
- **The browser pilot is clunky** until an embedding API exists: download, edit in another tab, save and upload. Its value is proving the hosting, the lease and save-to-revision, not the experience.
- **A 40 MB download** the first time a person opens a native file, 15 MB compressed, then cached.
- **A round trip per edit.** Every edit sends the whole file to the worker and back, and spawns a process. On the spike's small files that took milliseconds; on a large document it is the transfer and the parse, which phase 2 measures.
- **A worker service to run,** with its own image to build, pin and patch, in every deployment that turns it on.
- **The name.** `artifactr-craft` borrows the apps' brand, and WordCraft's `NOTICE` says the ArtCraft name, wordmark and logos are trademarks, outside the open-source licence. The neutral parts (manifest, blobs, sandbox) don't depend on the apps, so a neutral name costs nothing; see the unresolved questions.

## Alternatives

- **Convert to Markdown and back.** Uses what exists, and loses styles, comments, tracked changes and layout on every round trip.
- **Keep files outside artifactr,** with a link in an artifact. No revisions, no proposals, no attribution, and nothing for the agent to perceive.
- **LibreOffice headless** as the app. Mature, with every office format, but a large C++ process whose edits are UNO calls rather than commands, MPL-licensed, and harder to sandbox per call. It remains the obvious fallback if the craft apps don't mature, and the `CraftApp` port admits it.
- **Format libraries in Python** (`python-docx`, `openpyxl`, `python-pptx`). In-process, so no isolation from hostile files, and each format would grow its own edit model in the application's code: the scattered per-type behaviour ADR-0003 exists to prevent.
- **A CRDT per format, chosen by lattice.** True simultaneous editing, a lossy conversion of every format into it, and a research project per format. [Merge strategies](#merge-strategies) says why ordered operations on the server suit lattice better, and when that flips.
- **One adapter for every craft app.** Their control channels share a JSON-lines shape and `engine.execute`, but differ in authentication (two have none), method names, MCP tool names and flags, and their commands are all their own. A port with one adapter per app is honest about that.

## Unresolved questions

- **Will upstream take an embedding API** (D10)? If not, is an embedded editor worth a WebAssembly build of our own?
- **The agent's handle** in comments, and whether a comment can address a particular agent when an application has several.
- **The bridge's identity** (D14): committing as the person keeps attribution, but needs a person's token on a device, which grantr's service principals don't cover yet.
- **The name** of the package. `artifactr-files`, with `wordcraft` as an adapter module, avoids the apps' trademark; `artifactr-craft` was the working name.
- **The brand licence.** WordCraft's `NOTICE` puts the ArtCraft name and logos under `LICENSE-brand.txt`, which the spike didn't read. Whether serving the browser build as released is allowed, or its marks must be removed, is unverified, and affects D15.
- **Upstream's supply chain.** Checksums only, no signatures, SBOM or attestations, and a very young organization whose repositories gathered tens of thousands of stars in days. Whether to wait for signed releases before phase 4, or build the CLI from a pinned source commit in CI instead of taking the binary.
- **Quotas.** A per-workspace or per-tenant limit on blob bytes, beyond the per-blob limit, and where it is enforced.
- **Text extraction** for search across native files, which the text blob makes possible and nothing here builds.
- **When the blob port moves into artifactr,** if another package needs attachments, such as images in Markdown documents.

## Evidence

The spike that grounds this RFC, on 2026-10-16. Everything downloaded was treated as untrusted data, in a scratch directory outside the repository, and nothing was built from source.

### artifactr

- **The `test` operation guards a stale replace.** Against artifactr at `a267cf16`, `apply_patch` with `[{"op": "test", "path": "/content/sha256", "value": "aaa"}, {"op": "replace", "path": "/content", "value": {...}}]` applies to data whose digest is `aaa`, and on data whose digest has moved to `ccc` raises `PatchFailed: the JSON patch does not apply: ccc (<class 'str'>) is not equal to tested value aaa (<class 'str'>)`.
- **Proposals rebase by applying.** `core.rules._apply_change` applies an accepted edit's stored patch to the current version; only proposing checks `base_version`. Without the `test`, a stale whole-file replace would be accepted over newer revisions.
- **`render_for_agent(self) -> str`** is synchronous on the model (`core/artifacts.py`), and `read_artifact` and the capability's instructions call it directly.
- **Every revision stores its resulting data,** and `artifact_created` and `artifact_changed` carry data or a patch into relayr's bridged events.

### WordCraft

Read from a shallow clone of `main` at `eae24217` (2026-10-15) and the v0.7.0 release (2026-10-14, tag at `fc419188`), on 2026-10-16. "Verified" means read in the repository or seen running; "unverified" means not checked.

| Claim | Finding | |
|---|---|---|
| Licence | `LICENSE-MIT` and `LICENSE-APACHE`; `Cargo.toml` says `MIT OR Apache-2.0`. `NOTICE`: the ArtCraft name, wordmark and logos are trademarks, under `LICENSE-brand.txt`. Bundled fonts are OFL-1.1 | Verified |
| Releases | v0.1.0 to v0.7.0 between 2026-10-07 and 2026-10-14. Linux x86_64, aarch64 and riscv64 tarballs, packages and AppImages; macOS, Windows, FreeBSD; a web build; `SHA256SUMS.txt` | Verified |
| A Linux CLI | Only inside the full app's tarball (`bin/wordcraft-cli`, 69.6 MB, beside the 98.6 MB app); a standalone CLI archive exists for macOS only. Dynamically linked against the C library, `libm` and `libgcc_s` | Verified (aarch64) |
| Signatures, SBOM, attestations | None: nothing in `release.yml`, and GitHub's attestation API has none for the x86_64 tarball | Verified absent |
| Container image | None found: no Dockerfile in the repository, no registry references | Unverified (the registry's API wasn't readable with the token used) |
| Published crates | None on crates.io; the name `wordcraft` there is an unrelated crate. Using the crates as a library means a git dependency | Verified |
| MCP server | `wordcraft-cli mcp`, stdio only, line-delimited JSON-RPC, protocol `2025-06-18`. 16 tools; `--automation-read-root` and `--automation-write-root` confine file access | Verified, live |
| Control channel | In the desktop app: binds 127.0.0.1, a 256-bit key from a 0600 file, newline-delimited JSON, 1 MiB lines, 30 s to authorize | Verified in code, not run |
| Commands | 617 in `wordcraft-cli commands --json` for v0.7.0 (389 change the document), 629 `CommandSpec`s at `eae24217`; the README says 422 and `docs/mcp.md` "over 270". Parameters are free-text signatures, not JSON Schema. Commands serialize as `{command, params}`; macros exist in memory | Verified |
| Undo | Whole-document snapshots | Verified in code |
| Formats | Opens docx, doc (import only), odt, rtf, html, md, tex, txt, json, xml. Saves docx, pdf, odt, rtf, html, md, tex, txt, png, json, xml; all ten conversions of one test file succeeded | Verified, live |
| Network | No HTTP client in `Cargo.lock`, no telemetry or update checks. Sockets only in the control server, MCP's `--connect`, and a local Zotero client | Verified in code |
| Fonts | Bundled first, then user fonts, then system fonts from `/usr/share/fonts` | Verified in code |

### Running it

In a container on Docker 29.4.0, on an aarch64 host, from `debian:bookworm-slim` at `sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587`, with the release's aarch64 tarball (its checksum matched):

```sh
docker run --rm -i --platform linux/arm64 --network none --read-only \
  --memory 1g --cpus 1 --pids-limit 256 --tmpfs /tmp \
  -e HOME=/tmp -e WORDCRAFT_NO_PREFS=1 -e TZ=UTC \
  -v "$BIN":/app:ro -v "$CORPUS":/in:ro -v "$OUT":/out \
  debian@sha256:7c7b2c96... \
  /app/wordcraft-cli mcp --author "Spike Agent" \
    --automation-read-root /in --automation-write-root /out
```

A script of our own drove it over stdio. The corpus was six `.docx` files generated with Python's `zipfile`: headings, run formatting, lists and a bordered table; a footnote; an image; a comment; tracked insertions and deletions; and all of them together. No real-world documents were tested.

| Measure | Result |
|---|---|
| Start-up | About 4 ms for `--version` and 6 ms for MCP's `initialize`, inside the container. Starting a container took 0.4 to 8 s |
| Calls on the small files | `open_document` 1 to 12 ms, `inspect_document` 1 to 41 ms, `render_page` 3 to 18 ms, `save_document` 2 to 18 ms. Every call succeeded, `batch` and `edit.undo` included |
| `render_page` | A PNG as MCP image content, with the page's size and count; US Letter at scale 1 is 612 × 792 |
| Open and save, no edits | Kept exactly: paragraph count, styles, numbering, text, run properties (bold, italic, underline, colour, size, font), table borders and widths, the footnote, the comment and its author and date, the tracked changes' authors and dates, the image's bytes |
| Changed on save | Adds `docProps/app.xml`, `word/settings.xml`, `word/theme/theme1.xml`, and `word/commentsExtended.xml` where there are comments; renumbers tracked changes' ids; in `core.xml`, sets `dcterms:modified` to the clock, adds one to `cp:revision` and writes `--author` as `lastModifiedBy` |
| Determinism, two processes | PNG renders identical. `.docx` identical except `docProps/core.xml`'s dates; zip entries carry a fixed 1980 time. PDF differs in its dates and `/ID` |
| Failure | The first run used an amd64 image, because the host's Docker defaults to `linux/amd64`, and failed with `exec /app/wordcraft-cli: no such file or directory`. `--platform linux/arm64` fixed it. x86_64 was not run |

### The other apps

From [getartcraft.com/apps](https://getartcraft.com/apps) on 2026-10-16 and each repository under `github.com/storytold`. Each repository exists, has `LICENSE-MIT` and `LICENSE-APACHE` and a `MIT OR Apache-2.0` badge, and documents MCP in `docs/`. Formats are the READMEs' claims, not tested. Nothing but WordCraft was run.

| App | Site's maturity | Latest release | Formats claimed | Surface documented | Licence files | Run |
|---|---|---|---|---|---|---|
| WordCraft | In development (README: alpha) | v0.7.0 | docx, odt, rtf, md, tex, pdf | stdio MCP, control channel | Verified | Verified |
| DeckCraft | In development | v0.7.0 | pptx; pdf, png, jpeg, gif export | MCP, control channel | Verified | Unverified |
| GridCraft | In development | v0.7.0 | xlsx; csv, tsv; xls, xlsb, ods import | MCP, control channel | Verified | Unverified |
| PdfCraft | Early alpha | v0.8.0 | pdf: combine, redact, sign, forms, OCR | MCP, CLI | Verified | Unverified |
| PhotoCraft | Early alpha | v0.9.0 | psd | MCP, control channel | Verified | Unverified |
| VectorCraft | In development | v0.12.0 | svg, pdf, ai; raster export | MCP, control channel | Verified | Unverified |
| FigCraft | Early alpha | v0.6.0 | its own; svg, png, pdf; fig (best effort) | MCP, control channel | Verified | Unverified |
| DesignCraft | In development | v0.8.0 | its own; idml; indd import; pptx, pdf, epub export | MCP, control channel | Verified | Unverified |
| CADCraft | In development | v0.7.0 | dxf; dwg; svg, png, pdf export | MCP, control channel | Verified | Unverified |
| SoundCraft | In development | v0.7.0 | wav, aiff, flac; mp3, ogg, aac import; MIDI | MCP, control channel | Verified | Unverified |
| LightCraft | In development | v0.8.0 | camera raw, jpeg, png, tiff, webp, psd, jxl | MCP, control channel | Verified | Unverified |
| EffectCraft | In development | v0.10.0 | Lottie; video codecs; exr, psd | MCP, control channel | Verified | Unverified |
| FilmCraft | In development | v0.8.0 | video codecs; FCP7 XML, AAF, OTIO; subtitles | MCP, control channel | Verified | Unverified |

Every repository was created between 2026-09-30 and 2026-10-09, all thirteen were pushed to on 2026-10-16, and their stars run from about 1,900 to 64,700. A fourteenth repository, AniCraft, isn't on the page and has no licence GitHub detects.

### Events, the web build and merging

A second round, against the same WordCraft commit, `craft-libs` at `83bf4cb2`, DeckCraft at `1dc69720`, GridCraft at `f1894c6d`, PhotoCraft at `2a952f16` and FigCraft at `d1d8c3f6`, and every app's `Cargo.lock` at its head on 2026-10-16.

| Question | Finding | |
|---|---|---|
| Does WordCraft push anything? | No. Every write in the control server's loop answers the request just read. MCP declares no `subscribe` or `listChanged`, sends no notifications, and answers `resources/subscribe` with "method not found" | Verified in code |
| Can a person's edits be seen as commands? | Only after the fact. `edit.undoHistory` gives the undo stack's labels; `tools.recordMacro` records every command the session runs, read back with `tools.macros`, over the desktop control channel. Whether every interaction is captured (drags, dialogs) wasn't checked. GridCraft has `engine.journal`, "commands run so far (replayable)" | Verified in code; capture not tested |
| One protocol for every app? | No. `craft-libs` has no control or automation crate. All bind 127.0.0.1 and speak JSON lines with `engine.execute`, but WordCraft and PhotoCraft authenticate with incompatible handshakes, DeckCraft and GridCraft not at all, and their MCP tool names and bridge flags differ. Every repository has an `AGENTS.md` | Verified, for four apps' protocols |
| Saves | Atomic: a temporary file beside the target, `fsync`, then a rename | Verified in code |
| AutoSave and recovery | Desktop AutoSave is on by default, only for files saved this session; off in the browser. Recovery snapshots on the desktop only | Verified in code |
| Locks and outside changes | No lock files for documents, and nothing notices a file changed on disk, so AutoSave overwrites an outside change | Verified absent |
| Comments and tracked changes | Comments have a durable id, author, date, parent, resolved and anchors; tracked changes have kind, author and date. `inspect_document` gives counts and indexes only. `review.comments` and `review.changes` give author, date, anchor, text and id, run in the sandbox on the corpus. Accepting, rejecting and resolving act on the selection | Verified, live |
| How commands address content | By position and selection: a story, a path of block indexes and a byte offset. Paragraphs, tables, rows and cells have no ids; comments, bookmarks and pictures do | Verified in code |
| CRDT or OT | No CRDT or OT library in any of the thirteen lock files. FigCraft has its own collaboration: property-level change sets, server-ordered last-writer-wins, over WebSockets. WordCraft lists real-time co-authoring as a gap | Verified |
| The web build's API | None: the JavaScript exports only its initializer; no `postMessage`; open by picker, drag and drop or paste; save by `showSaveFilePicker` or download | Verified in the release files and code |
| Its size and hosting | `wordcraft-web-0.7.0.zip`, checksum matched: 11 files, 40,011,614 bytes; the WebAssembly is 39,785,016 bytes, 14.9 MB with `gzip -9`. SRI on its script and WebAssembly. No COOP or COEP, no `SharedArrayBuffer`, no workers. Its `HOSTING.md` expects iframing, asks that no restrictive `frame-ancestors` be sent, and lists the sandbox flags it needs | Verified; not served or run |
| Its CSP | `wasm-unsafe-eval` and the inline module script; `blob:` for downloads | Inferred from the files, not tested |
| Calling home | No URLs in the JavaScript beyond fetching its own WebAssembly; the WebAssembly's URLs are namespaces and About links. No remote fonts | Verified by search |
| The same engine as the CLI | Yes: the web build and the CLI both depend on WordCraft's engine and document crates. Whether a browser save matches the worker's bytes wasn't run | Verified in the manifests |

[a-adr-0001]: ../artifactr/adr/0001-python-library-with-sans-io-core.md
[a-adr-0002]: ../artifactr/adr/0002-single-write-path.md
[a-adr-0003]: ../artifactr/adr/0003-artifact-types-as-pydantic-subclasses.md
[a-adr-0004]: ../artifactr/adr/0004-optimistic-concurrency-and-revisions.md
[a-adr-0005]: ../artifactr/adr/0005-one-event-log-per-workspace.md
[a-adr-0008]: ../artifactr/adr/0008-agent-perception-and-steering.md
[a-adr-0009]: ../artifactr/adr/0009-write-policies-and-non-blocking-proposals.md
[a-adr-0017]: ../artifactr/adr/0017-application-toolsets-and-capability-events.md
[a-adr-0019]: ../artifactr/adr/0019-storage-protocol-and-workspace-handles.md
[a-adr-0021]: ../artifactr/adr/0021-sql-storage.md
[a-adr-0028]: ../artifactr/adr/0028-typed-feedback-as-events.md
[a-adr-0033]: ../artifactr/adr/0033-trace-links-on-runs-and-revisions.md
[a-adr-0034]: ../artifactr/adr/0034-ports-and-adapters-for-integrations.md
[a-adr-0036]: ../artifactr/adr/0036-metric-cardinality-through-sdk-views.md
[a-adr-0038]: ../artifactr/adr/0038-feedback-as-scores.md
[a-adr-0062]: ../artifactr/adr/0062-restricted-items-left-out-of-every-read.md
[a-adr-0066]: ../artifactr/adr/0066-row-level-security-under-the-scoping.md
[s-adr-0035]: ../stackr/adr/0035-the-thin-images.md
