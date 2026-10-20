# ADR-0009: Each crafting app declared once, on one of two dialects, pinned on its own

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland
**Amends:** [ADR-0005](0005-wordcraft-headless-pinned-by-checksum.md), whose pin, script and fidelity report were WordCraft's alone

Groundwork for the crafting apps after WordCraft, in [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md). Nine are integrated as native files (WordCraft, GridCraft, DeckCraft, PdfCraft, CADCraft, PhotoCraft, VectorCraft, DesignCraft, FigCraft), and four as export only (FilmCraft, EffectCraft, SoundCraft, LightCraft), whose projects point at media outside them.

## Context

All thirteen apps release the same assets: Linux tarballs and a macOS zip holding `<app>-cli`, a browser build, and `SHA256SUMS.txt`, with no signatures. Each CLI's `mcp` is an MCP server on stdio. On 2026-10-18 we ran each pinned release's CLI and listed its tools and options; where an app's sources say otherwise, the release is what is recorded here:

- **Two dialects.** Seven servers have a tool for each step, as WordCraft's has (`open_document`, `batch`, `save_document`, `list_commands`), under each app's own names (`open_workbook`, `save_presentation`, `open`, `save`). Six run every step as a command, through `command_run`, `command_batch`, `command_list`, `doc_inspect` and `render_preview`, as PdfCraft's and FilmCraft's do. Within that dialect PdfCraft opens a file by its `file.open` command and names the document in every command after, while PhotoCraft refuses `file.open` and opens through a tool of its own, `doc_open`.
- **Confinement differs by release.** WordCraft, PhotoCraft, VectorCraft, DesignCraft, EffectCraft and SoundCraft take a read root and a write root. PdfCraft 0.8.0 takes one `--root`, though its sources have since gained the two. GridCraft, DeckCraft, CADCraft, FigCraft, FilmCraft and LightCraft confine nothing: their CLIs read and write wherever their user can. DeckCraft's and FigCraft's sources have roots, but no release has them yet.
- **Headless pages.** Every app's server renders a page as a PNG but GridCraft's, FigCraft's and SoundCraft's, which have only a screenshot of the desktop app, an export, or a mix-down.
- **Notices.** PdfCraft's Linux tarballs carry its OCR's two models under CC-BY-SA-4.0, with their attribution and licence files beside them; its CLI-only tarballs and its browser build carry none. No other release ships a third-party model.
- **The brand.** Each app's brand licence is WordCraft's, word for word but the app's name: the brand's marks only in unmodified official builds, never in the name of anything else.

## Decision

- **`artifactr.files.craft` declares every app once.** A `Craft` names the app (its key `files:<name>`, its CLI `<name>-cli`, its repository `storytold/<name>`), its `dialect` (`tools` or `commands`), its `roots` (`split`, `single` or `none`), the `formats` it keeps, whether it can `render` headless, the host surface its browser build has (`bridge`: `parent` or `global`), its `reach` (`file`, kept as a native file, or `export`, only what it renders), and its `notices`. `CRAFTS` holds the thirteen, as their pinned releases offer them. Formats with no registered media type (FigCraft's, and the native formats of VectorCraft and DesignCraft) are left to their adapters.
- **Each is an integration of lattice-core's registry,** `files:<name>`, off by default but WordCraft's, which stays on. lattice-core can't import artifactr, so its registry holds each key's default and description, and `Craft.integration` reads them from it; a test holds `KNOWN`'s `files:` keys to `CRAFTS`, in order, as portalr's tests hold its generated copy to `KNOWN`.
- **`Spawn` is the one place a CLI starts:** for every call, in an empty temporary directory that holds its root or roots, with the call's deadline, the version check, and the mapping of what goes wrong onto `AppFailed`, which were WordCraft's adapter's. It passes the roots its app takes. **An app whose CLI confines nothing is spawned only with `trusted=True`**, the operator's word that its files are trusted or that the process is already confined; without it, `Spawn` raises `ValueError` as it is made, so a deployment can't run one by accident. Those apps' keys stay off by default for the same reason.
- **The worker is an `App` that forwards the call.** The sandboxed worker of RFC-0003's phase 3 is a separate job. On the application's side it is an `App` that sends each call to the worker; inside the worker, the same adapter and its `Spawn` run, with `trusted=True`, since the sandbox confines what the CLI can reach. Nothing in a dialect or an app's adapter changes for it.
- **Two dialect bases, over one `Headless`.** `Headless` is an `App`: `apply`, `inspect`, `render` and `commands` each spawn the CLI, open the source or make a blank file, and take their steps. `open` returns what the server calls the file it opened, which every later step is given. `ToolsDialect` takes each step with a tool its subclass names (`new_tool`, `open_tool`, `save_tool`, `batch_tool`, `render_tool`, `list_tool`); its servers hold one file, so it names none. `CommandsDialect` takes each with a command (`open_command`, `save_command`, `new_command`), naming the open document by `handle`, `doc` by default, as the open command's result names it; a result that names none is a crash, and a batch whose results say a step failed is refused, whatever its reply's error flag. A step a server takes otherwise is overridden. A subclass that reads files and names no `craft` or `extension` is refused as it is defined. How a file is read into an `Inspection` is each app's own, `inspection`. An app that can't render refuses a page before any CLI starts.
- **WordCraft's `Subprocess` is the first `ToolsDialect`,** with its signature, its tools, its messages and its fidelity unchanged; its inspection and its `.docx` fingerprint stay in `artifactr.files.wordcraft`.
- **`scripts/craft <app> cli|web|notices`** replaces `scripts/wordcraft`, with a pin for each app in `scripts/crafts/<app>.sha256`: the release's `SHA256SUMS.txt` lines for one asset on each of Linux x86_64 and aarch64 (the full tarball or the CLI-only one), the macOS CLI, and the browser build. A pin naming two assets for one target is refused before anything is downloaded. Each asset is fetched when it is first asked for, and only then. `notices` prints the licence, notice and attribution files beside the CLI, for whatever ships it. A test holds every pin to that shape and to `CRAFTS`.
- **The notices travel with the CLI.** PdfCraft's pin is its full tarballs, whose OCR models' CC-BY-SA-4.0 attribution its `Notice` records, with the files that carry it; whatever ships PdfCraft's CLI, such as the worker's image, ships them. A browser build is served as released, its own licence files with it.
- **The brand's name appears in no key, title, description or document of lattice's** but RFC-0003's record of the licence, which a test holds the registry to.
- **The fidelity report is each app's,** from a corpus of its own: `tests/files/corpus/<app>/`, one generated file per feature, read by a `Corpus` that says how each feature's value is read and what two saves in a row must keep. `moon run artifactr:fidelity` runs the app `CRAFT` names, WordCraft by default, and Nightly's `fidelity` job runs one app of its matrix each; the matrix lists the apps with a corpus, which a test holds it to. Its live tests are marked `craft("<app>")`, and run only where `ARTIFACTR_TEST_CRAFT` names the app.

## Options considered

### Option A: A registry, two dialect bases, and an adapter for each app (chosen)

| Dimension | Assessment |
|---|---|
| Fit | The two dialects the thirteen servers speak, with each app's differences in a subclass |
| Safety | The confinement each release offers is declared, and an app without it needs a word from the operator |
| Cost | One adapter, one corpus and one pin for each app, on shared code |

### Option B: An adapter for each app, written from scratch

**Cons:** thirteen copies of the spawn, the deadline, the error mapping and the version check, which ADR-0005 wrote once and which every worker call depends on.

### Option C: One adapter, driven by a table of tool names

**Cons:** the servers differ in more than names. Within one dialect, one app opens by a command and another refuses that command and opens by a tool; one names the document in every command, another acts on the one open. A table that holds that is code.

## Trade-off analysis

The dialect bases hold what is the same and leave what isn't to each app; the registry says once what each release offers, so the switch, the pins and the docs can't disagree with it.

## Consequences

- Easier: an app's adapter is its tool or command names, the steps its server takes otherwise, and its `inspection`; its corpus and pin plug into the harness and the script.
- Easier: a release that gains roots, or a render, is one field changed, and a test says what follows from it.
- Harder: six apps can't run on untrusted files until the worker exists; their keys stay off.
- Harder: every app's talk level is still `save`. The shim that reaches a build's host surface, and the level it gives, is a decision of its own.
- Revisit: each descriptor with each pin raised; PdfCraft's to `split` once a release takes the two roots; DeckCraft's and FigCraft's likewise. `Headless` makes its own `Spawn`; a confinement that wraps the CLI where it runs, such as a command prefix, would add a parameter for it.

## Action items

1. [x] `artifactr.files.craft`: `Craft`, `CRAFTS`, `Spawn`, `Headless`, `ToolsDialect`, `CommandsDialect`; WordCraft on `ToolsDialect`.
2. [x] The keys in lattice-core's registry, and portalr's generated copies.
3. [x] `scripts/craft`, a pin for each app, and their tests.
4. [x] The fidelity harness and Nightly's `fidelity` job, by app.
5. [ ] Each app's adapter, corpus, normalizer and type, by its own work.

## Notes

- 2026-10-20: GridCraft's, DeckCraft's and PdfCraft's adapters, types and corpora. Each corpus covers only what it generates; not covered: GridCraft's charts, pivots, images, sparklines and data bars; DeckCraft's charts, its masters and layouts beyond one, embedded media and animations; PdfCraft's signatures (which its full rewrite on save invalidates), annotations beyond text notes and links, encryption, XFA and incremental updates. What the adapters read in-process is bounded: a package's inflated parts by `limit`; a canonical package's XML parts (DeckCraft's) at 16 MiB each, 500,000 elements in all and 256 deep; a PDF's object streams by `limit`, read in one pass.
