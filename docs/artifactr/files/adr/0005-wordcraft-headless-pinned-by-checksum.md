# ADR-0005: WordCraft headless, pinned by checksum, and what each app declares

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** [ADR-0004](0004-an-app-is-a-port-of-stateless-calls.md), which left an app's talk level for the first adapter that needed it

Records phase 2 of [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md#phases): WordCraft's first adapter, its fingerprint, and its fidelity report.

## Context

WordCraft v0.7.0's `wordcraft-cli mcp` is an MCP server on stdio with sixteen tools: it opens one document, runs commands on it (`batch`, `execute`), saves it, and reads it (`get_text`, `inspect_document`, `render_page`, `list_commands`), confining every file it touches to a read root and a write root it is given. It replies to a failed command with the batch's steps, stops at the first that failed, and stamps `docProps/core.xml` with the time, a revision count and the author on every save. Upstream publishes `SHA256SUMS.txt` with each release, and no signatures.

Each app also differs in how it talks to a person's copy of it: WordCraft's browser build opens and saves files only, and its host bridges, `storytold/wordcraft#405` and `#1655`, are open, unmerged, on 2026-10-17. And lattice-core's Integrations switch keys each crafting app on its own, `files:wordcraft` first.

## Decision

- **`artifactr.files.wordcraft` is WordCraft's layer,** beside the port, and imports only it, the manifest, pydantic, `mcp` and `anyio`, which the `files` extra now brings. A call's deadline is anyio's, since the MCP client ends the CLI in a shielded scope that only anyio's cancellation lets finish, so a call past its deadline leaves no process behind.
- **`Subprocess` spawns `wordcraft-cli mcp` for every call,** in an empty temporary directory that is its read root and its write root, and nothing else; the source is written there, and the result saved there. The process and the directory end with the call, so no document stays open between calls (ADR-0004). It is not a sandbox: the CLI runs as the caller's user, with its network. It is for tests and trusted files; the worker that runs hostile ones is phase 3.
- **A call maps onto WordCraft's tools:** `apply` opens the source, or a blank document, runs the batch as one `batch` call, and saves; `inspect` reads the text, the structure, `review.comments` and `review.changes`; `render` is `render_page`; and `commands` is `list_commands`, ten at most. A failed tool is `refused`, with its message, or for a batch with the command that failed; a call past its deadline is `timeout`; and a CLI that exits, or whose replies make no sense, mid-call, is `crashed`, with what ended it and the end of what it printed. It runs in no image, so its `build` is None.
- **The CLI's version must be the adapter's,** which provenance records, so a CLI swapped under a deployment is refused, not recorded under another version.
- **The fingerprint is read from the bytes, in Python,** not asked of the app: the SHA-256 of each part's name and its own SHA-256, in order of name, without `docProps/core.xml`, so no two different files share one. Each part is read as it inflates, and parts past the adapter's limit, 256 MiB by default, are `too_large`, so a zip bomb is refused before it is whole; a zip that is corrupt, encrypted or names a part twice is `refused`.
- **The outline is the headings,** `Title` and `Heading1` to `Heading9`, by id or name and indented by level, or each block's first line if there are none, to 4,000 characters.
- **Each app declares two more things:** `talk`, how much it talks to the host while a person edits in it, one of RFC-0003's levels (`save`, `commands`, `polled`, `pushed`), and `integration`, the key that switches it in a workspace. WordCraft's are `save` and `files:wordcraft`; the fake's are `save` and `files:fake`. They are declarations only: what reads them is phase 3's switch and phase 4's check-out.
- **WordCraft is pinned by checksum:** `scripts/wordcraft.sha256` holds the release's `SHA256SUMS.txt` lines for the Linux tarballs, the macOS CLI and the browser build, and `scripts/wordcraft cli|web` downloads one once, checks it, unpacks it and prints its path, as `scripts/tlc` does for TLC (RFC-0003's D8).
- **The fidelity report runs nightly** as `artifactr:fidelity`: the pinned CLI opens and saves each file of `tests/files/corpus/docx/`, one generated file per feature, compares each feature's value before and after, and saves again, which must change nothing but the stamp. Its matrix is Nightly's job summary. A feature the pinned release is known not to keep is listed as such, and expected to fail, so Nightly turns red only when the matrix changes. RFC-0003 says the report compares normalized OOXML; it compares, instead, each feature's value read out of the OOXML (its text, styles by name, list formats, comments and their anchors, and so on), leaving out what a save may rewrite without changing the feature, such as ids numbered again. The corpus and the values it is compared by run on every pull request, against a stand-in for the CLI that speaks its tools, as does every branch of the adapter.

## Options considered

### Option A: The CLI's MCP server, a fresh one per call (chosen)

| Dimension | Assessment |
|---|---|
| Isolation | The CLI's own roots confine its files to the call's directory |
| Fit | One process per job is what the worker will run |
| Cost | A spawn and an MCP handshake per call |

**Pros:** the same dialogue runs in the worker later; no state between calls.
**Cons:** a call that reads and inspects spawns once and asks four tools.

### Option B: The CLI's one-shot commands (`run`, `info`, `inspect`, `render`)

**Cons:** `run --cmd` confines nothing: a command that opens a file, such as inserting a picture or a mail merge's data, reads anywhere the user can.

### Option C: A server kept open across calls

**Cons:** a document or a process between calls is state the worker must isolate and clean up, which ADR-0004 rules out.

## Trade-off analysis

A spawn per call is cheap next to a call's seconds of deadline, and buys the confinement and statelessness the worker needs, with the same code.

## Consequences

- Easier: the worker in phase 3 runs `Subprocess` inside its sandbox, and adds only the transport.
- Easier: raising the pin is checked feature by feature: run `moon run artifactr:fidelity` with the new release before the pull request that raises it, since CI runs the report only nightly, on the release pinned on `main`.
- Harder: the corpus is generated, so the report says nothing yet of real-world documents; documents whose licences allow it can join it. Nor does it measure large documents' round trips, which RFC-0003 asks of phase 2; that is deferred to the worker, phase 3, where the round trip includes its transport.
- Revisit: the pin, with each WordCraft release, raised by hand after `moon run artifactr:fidelity` passes on it; `talk`, when a WordCraft host bridge ships in a release.

> **Amended (2026-10-26) by [ADR-0010](0010-a-shim-beside-the-build-and-talk-level-one-plus.md):** the bridge shipped in WordCraft 0.11.0, which is pinned, so `talk` is `bridged`; the host bridges named above were superseded by `#3822`.

## Action items

1. [x] `Subprocess`, `fingerprint` and `outline`, with `talk` and `integration` on `App`.
2. [x] `scripts/wordcraft` and its pin; the corpus; `artifactr:fidelity` in Nightly.
