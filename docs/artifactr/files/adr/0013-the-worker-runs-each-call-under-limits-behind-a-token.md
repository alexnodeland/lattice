# ADR-0013: The worker runs each call under limits, behind a token, one job at a time

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** lattice RFC-0003's phase 3 exit, which asked a typed failure of every hostile file
**Amended by:** [stackr ADR-0043](../../../stackr/adr/0043-native-files-in-the-template.md), which runs a worker for each app

Records the package's half of the worker of [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md#the-app-port-and-the-worker), phase 3: the worker program, its limits, and the `App` that calls it. Its container, network and image are stackr's.

## Context

`Subprocess` runs WordCraft's CLI in the application's own process tree, as its user, with its network ([ADR-0005](0005-wordcraft-headless-pinned-by-checksum.md)): it is for tests and trusted files, and until now every check-in and every agent's edit went through it. RFC-0003 puts hostile files in a worker instead: a service on an internal network that only the application joins, called over HTTP with a token the deployment generates, running one job at a time, with a deadline, `setrlimit` limits on CPU time, address space and file size, and a limit on the reply, each breach a typed failure. [ADR-0009](0009-each-crafting-app-declared-once-on-one-of-two-dialects.md) settled that the worker runs the same adapter and `Spawn` inside its sandbox, and that on the application's side it is an `App` that forwards each call; it left open how the limits wrap the CLI, and named a command prefix.

## Decision

- **`artifactr.files.worker` is a layer of its own,** in the `files` extra, which gains `starlette`, `uvicorn` and `httpx`: `worker_app`, the worker, over any `App`; `Worker`, the application's side; and `Limits`.
- **`Limits` holds what each call may take:** an edit's, inspection's or lookup's deadline (30 s), a render's (10 s), the CLI's CPU seconds (30), address space (2 GiB) and largest file (256 MiB, which is also the most a sent file may hold, and what the adapter inflates against), and the reply's size (384 MiB, the largest file in base64 with its reading). A call's deadline is the caller's, at most the limit's. The container's own limits, on memory, CPU, processes and its `tmpfs`, are stackr's.
- **What the launcher sets, and what it leaves to stackr.** It sets `RLIMIT_CPU`, `RLIMIT_AS` and `RLIMIT_FSIZE` on the CLI, and its children inherit them, each with its own count of CPU time. It sets no limit on processes (`RLIMIT_NPROC`, per user, which the container's PID limit bounds better), open files (`RLIMIT_NOFILE`) or core dumps (`RLIMIT_CORE`), and nothing on the network or the `tmpfs` the call's directory is in: those are the container's, stackr's. WordCraft's `wordcraft-cli` 0.7.0 is a native executable linked against glibc alone, with no runtime of its own; on Linux aarch64 its live tests and the hostile corpus pass under the default 2 GiB of address space.
- **The CLI is started under a launcher.** `Spawn`, `Headless` and `Subprocess` take `launcher`, a command the CLI and its arguments are given to, empty by default. `Limits.launcher()` is `python -I confine.py --cpu … --memory … --files … --`, which sets the three limits by `setrlimit`, soft and hard, and `exec`s the CLI, so they hold in the CLI's own process, and nothing of lattice is imported to start it. A breach ends the CLI mid-call, which `Spawn` already reports as `crashed`. macOS refuses a limit on the address space, and enforces none, so there the launcher sets none; the image is Linux.
- **The wire is one request a call.** `GET /` says which app the worker runs: its name, version, image's digest (`WORKER_BUILD`, since only the deployment knows it), talk level and switch. `POST /apply`, `/inspect`, `/render` and `/commands` take the file as the body and the call as JSON in the `Worker-Call` header; an empty body to `/apply` is a new file. Replies are JSON, the new file in base64 within `/apply`'s, but a render's, which is its PNG. A failure is 422 with its `failure` and message, which `Worker` raises as the same `AppFailed`; a sent file past the limit is refused as `too_large` before it is all read, as is a reply past its own. The call's JSON is ASCII, every other character escaped, since a header's bytes are read as Latin-1, and at most 64 KiB, `CALL_LIMIT`, measured as sent. Every request without the token, `Authorization: Bearer` and nothing else, compared in constant time, is 401, and `worker_app` refuses to be made with an empty token. A reply the worker can't build from what the app returned is `crashed`.
- **One job at a time, waiting within its deadline.** A call that arrives while another runs waits for its turn, and the wait counts against its deadline: what is left is what the app is given, and a call that never gets its turn, or gets it with nothing left, fails as `timeout`, saying the worker was busy. A client that disconnects doesn't cancel its job, which runs to its own deadline. A worker scales by adding containers.
- **`Worker.connect(url, token=)` asks the worker which app it runs,** and is that app: its name, version and build are the worker's, so provenance records the image. The deadline and five seconds' grace bound the whole exchange; past them the call is `timeout`. A worker that can't be reached, replies with another status, or replies with what isn't a call's reply, is `crashed`.
- **`python -m artifactr.files.worker` runs it over one app,** from `WORKER_TOKEN`, `WORKER_APP` (`wordcraft` by default, or any other app whose files lattice keeps), `WORKER_CLI`, `WORKER_VERSION` and `WORKER_BUILD`, under `WORKER_LIMITS`, the deployment's `Limits` as JSON, which stackr's recipe sets, on `WORKER_HOST` and `WORKER_PORT`, 127.0.0.1 and 8080 by default. stackr's recipe must set `WORKER_HOST` to the worker's address on the internal network, since loopback would reach no one. uvicorn reads a request's head up to the longest call and its other headers, which a test sends over a real socket on loopback.
- **The hostile corpus is generated, never committed:** a zip bomb (a part that inflates to 4 GiB), nested XML (a million elements deep), and a PNG whose header says 65,535 pixels a side. Through the worker over WordCraft 0.7.0, the bomb and the nesting are refused by WordCraft's own limits, as `refused`, and the image is read without decoding its pixels, as one page with no text, rendered as a small PNG; each ends within its deadline. So RFC-0003's exit, a typed failure for every hostile file, is amended: every hostile file ends within its deadline, in a typed failure or in a reading that holds to every limit. It runs with the live tests, `craft("wordcraft")`, in Nightly's fidelity job; on every pull request, a stand-in CLI past each `setrlimit` limit is ended as a crash.

> **Amended (2026-10-20) by [stackr ADR-0043](../../../stackr/adr/0043-native-files-in-the-template.md):** the entry point served WordCraft alone, from `WORDCRAFT_CLI` and `WORDCRAFT_VERSION`, and GridCraft's, DeckCraft's and PdfCraft's adapters didn't pass the launcher on, so a worker over them would have run their CLIs with no `setrlimit` limits. It now runs any app by `WORKER_APP`, `WORKER_CLI` and `WORKER_VERSION`, every adapter takes `launcher`, and an app whose CLI confines nothing runs trusted, as the consequences below have it. `WORKER_LIMITS` empty is every default. `Worker.at(url, token=)` makes the app without a request, for an application that builds its parts before its event loop runs, and `open()` asks the worker which app it runs.

## Options considered

### Option A: A launcher that sets the limits and `exec`s the CLI (chosen)

| Dimension | Assessment |
|---|---|
| Fit | `Spawn` stays the one place a CLI starts; the limits are one parameter |
| Safety | The kernel's limits, in the CLI's own process, outliving the `exec` |
| Cost | One interpreter's start per call |

### Option B: `preexec_fn` on the CLI's process

**Cons:** `mcp`'s `stdio_client` makes the process and offers no hook, and `preexec_fn` is unsafe with threads.

### Option C: Limits on the worker's own process, inherited by every CLI

**Cons:** the CPU time and address space would be the worker's as well as the job's, so one long-lived worker would run out of them.

### Option D: Refuse a call while another runs

**Cons:** the caller can do nothing but retry; waiting within the deadline gives it the same answer when the worker stays busy, and a result when it doesn't.

## Trade-off analysis

The launcher costs an interpreter's start on each call, which is small beside the CLI's own, and buys limits the kernel enforces on the CLI alone, with nothing in an adapter or a dialect changed.

## Consequences

- Easier: an application points `NativeFiles` at `await Worker.connect(url, token=…)` instead of `Subprocess`, and nothing else changes; the same worker serves any app with an adapter.
- Easier: an app whose CLI confines nothing can run in the worker with `trusted=True`, since the worker is the confinement.
- Harder: a `crashed` failure's message carries the end of what the CLI printed, which a hostile file can shape. It is for the operator's logs; an application must not relay it to people or to an agent as it is.
- Harder: every call sends the whole file over the internal network, and the reply carries it back in base64.
- Harder: a call's header carries its commands, so one batch's JSON is at most 64 KiB, `CALL_LIMIT`; `Worker` refuses a longer one as `too_large` before sending it, and the entry point has uvicorn read a request's head that far.
- Met elsewhere: the scripted-model tests of phase 3's exit, for an edit, a proposal, a busy refusal and a conflict, are the agent's tools' ([ADR-0006](0006-the-agents-tools-behind-each-apps-switch.md)).
- Deferred: stackr's half, the worker's image built from the pinned release and pinned by digest, its internal network with no route out, the container's limits and read-only root, the `native_files` question, the token, and the check that the image's and the editor's pins agree; and the test that egress from the worker fails, which needs that network.

## Action items

1. [x] `artifactr.files.worker`: `Limits`, the launcher, `worker_app`, `Worker` and the entry point; `launcher` on `Spawn`, `Headless` and `Subprocess`.
2. [x] The hostile corpus, and the tests of each limit.
3. [x] stackr: the image, the recipe, the internal network, `WORKER_HOST`, the token and the release pin check (lattice RFC-0003): [stackr ADR-0043](../../../stackr/adr/0043-native-files-in-the-template.md), a worker for each app in a generated application.
4. [x] The test that egress from the worker fails, on stackr's network: stackr's `scripts/check-files`, in CI's "Native files" job on amd64 and arm64.
