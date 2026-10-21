# ADR-0043: Native files in the template: a worker for each app, with no route out, and its editor on a loopback origin

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland

Records stackr's half of the worker in [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#stackr)'s phase 3, which native files [ADR-0013](../../artifactr/files/adr/0013-the-worker-runs-each-call-under-limits-behind-a-token.md) left to stackr: the image built from the pinned releases, the internal network with no route out, the container's limits, the token and the release-pin check. It adds the template's `native_files` question, which wires native files into a generated application, and serves each bridged app's browser build on an origin of its own, for portalr's check-out ([portalr ADR-0049](../../portalr/adr/0049-checking-a-native-file-out-and-in.md)) and lattice's shim ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)).

## Context

artifactr's `files` extra has native files' types, stores, routes, agent tools, the editor's server and the worker program. Each crafting app's adapter runs its pinned CLI, and `python -m artifactr.files.worker` serves one app behind a token, one job at a time, with `setrlimit` limits on each call. Until now nothing ran it: a generated application had no files routes, no worker and no editor, so the portal showed native files nowhere.

What ADR-0013 deferred to stackr:

- the image, from the pinned release, its CLI checked against the pin's SHA-256 before use;
- a network with no route out, joined only by the application;
- the container's own limits: memory, CPUs, processes, a read-only root, its `tmpfs`;
- `WORKER_HOST` on that network, and the token the deployment generates;
- the check that a worker's CLI and its editor's build are one release;
- the test that egress from the worker fails.

Three things settled the shape:

- **The worker served only WordCraft, and limited only WordCraft.** Its entry point read `WORDCRAFT_CLI`, and GridCraft's, DeckCraft's and PdfCraft's adapters didn't pass the launcher on, so their CLIs would have run with no `setrlimit` limits at all. This change makes the entry point serve any app by `WORKER_APP`, `WORKER_CLI` and `WORKER_VERSION`, with every adapter's CLI under the launcher, and FreeCAD's ([files ADR-0014](../../artifactr/files/adr/0014-freecad-on-a-third-dialect-and-no-python-a-file-or-an-agent-brings.md)) among them.
- **`Worker.connect` is asynchronous,** and an application builds its parts, `NativeFiles` and its routes among them, before its event loop runs. `Worker.at(url, token=)` now makes the app without a request, and the application `open`s it as it starts.
- **A generated application has no `scripts/crafts`.** It installs lattice's libraries from GitHub ([ADR-0018](0018-the-template-pins-the-libraries-at-its-own-commit.md)), and its image is built from its own directory.

## Decision

### The question, and which apps run

- **`native_files`, on by default with artifactr,** adds the plumbing: `files.py`, the `files` extra, the workers' and editors' services, their image targets, and the pins. No app runs until `FILES_CRAFTS` names it, so a new application starts as it did. Native files' tables are migrated either way, so starting an app later needs no migration.
- **`FILES_CRAFTS` in `.env`, or `make up FILES="wordcraft gridcraft"`,** names the apps. Each is a Compose profile, `files-<app>`, which `make up` adds for each, and the application is told the same list. Its `depends_on` waits for each started worker to answer, and passes over one that isn't started (`required: false`, which needs Compose 2.20 or later).
- **Each running app is an integration,** `files:<app>`, which the application installs with grantr (ADR-0041) only while `FILES_CRAFTS` names it, and gates every surface with (`integration_gate`, with `ui_key_of` where forms are on too). Each keeps lattice-core's default: WordCraft, once named, is on in every workspace of every tenant until an admin switches it off; the others are off until an admin switches them on. Their default stays off while each app's own corpus and hostile files are still to come ([files ADR-0011](../../artifactr/files/adr/0011-a-gate-for-each-app.md)'s second action item, open for every app but WordCraft).

### The application's side

- **`Files`, in `files.py`,** makes a `Worker` for each running app, at `http://files-<app>:8080`, with that worker's own token, `FILES_<APP>_TOKEN`; `NativeFiles` over them, with SQL stores on the application's database, kept apart by tenant as artifactr's tables are, or in memory without one; `files_router`, mounted beside artifactr's at `/artifactr/v1` with the same `resolve_actor`; and the agent's tools. `Collaboration` registers the running apps' types, gates them, and opens the workers as the application starts. A worker that doesn't answer, or answers with what isn't a worker's hello, or runs another app or another version than its pin, stops the start, saying which.
- **With the portal, `Site.editors`** names each running bridged app's editor, `http://127.0.0.1:<port>/` by default, or `FILES_EDITORS` where people reach it another way.

### The image

- **Two targets of the application's own Dockerfile,** built for one app each (`CRAFT`, and the `VERSION` its pin names), rather than an image stackr releases: the worker and the application install artifactr from the same `uv.lock`, so the two ends of the wire are one version.
  - **`files-worker`:** the application's virtual environment and the app's CLI, as user 10002, running `python -m artifactr.files.worker` on `0.0.0.0:8080` of its container (`WORKER_HOST`), with `WORKER_SWEEP=1`.
  - **`files-editor`:** the virtual environment and the app's browser build, as user 10003, running `<package>.editor`, `editor_app` with the shim for the app and `PORTAL_URL`.
- **The release is fetched by lattice's own `scripts/craft`, and pinned by lattice's own `scripts/crafts/<app>.sha256`,** copied into the template as `scripts/craft` and `scripts/crafts/`. Each asset is downloaded, checked against its pin's SHA-256, and only then unpacked. The CLI's release is unpacked whole into `/opt/craft`, for the build's Linux, x86_64 or aarch64, so its libraries, licences and notices travel with it: PdfCraft's OCR models' attribution and CC-BY-SA-4.0 licences among them ([files ADR-0009](../../artifactr/files/adr/0009-each-crafting-app-declared-once-on-one-of-two-dialects.md)). FreeCAD's is its AppImage, unpacked by itself; its script confines nothing, so it runs only trusted, which the worker is, and it has no browser build, so no editor (files ADR-0014). The browser build is copied as released, which the apps' brand licence asks of their marks.
- **The release-pin check is `scripts/check-template`'s:** the template's `scripts/craft` and each pin must be byte for byte lattice's, its pins exactly the apps of `copier.yml`'s `crafts`, and each app's version there the one its pin names. A worker's CLI and its editor's build come from one pin file, so they can't be two releases; and lattice's tests ran that release.

### The container

| | A worker | An editor |
|---|---|---|
| Root filesystem | Read-only | Read-only |
| Writable | `/tmp`, a `tmpfs` of `FILES_WORKER_TMPFS` (1 GiB), `noexec,nosuid,nodev`: each call's directory | Nothing |
| User | 10002, not root | 10003, not root |
| Capabilities | None (`cap_drop: [ALL]`), and `no-new-privileges` | The same |
| Init | Docker's, `init: true`, which reaps what a call leaves | The same |
| Memory and swap, CPUs, processes | `FILES_WORKER_MEMORY` (3 GiB), no swap beyond it, `FILES_WORKER_CPUS` (2), 128 | 256 MiB, no swap beyond it, 64 |
| Seccomp, AppArmor | Docker's defaults; nothing here sets them | The same |
| Network | `files-<app>`, `internal: true`, its own; no port published | `editors`, its own, which has a route out; its port published on `APP_BIND`, 127.0.0.1 |
| Health | `GET /` with its token, from inside | `GET /`, from inside |

- **Each worker is alone on a network of its own,** `files-<app>`, internal: Docker gives it no route out, and only the application joins it besides, reaching the worker by its service's name. No worker reaches another.
- **Nothing outlives a call.** A CLI starts in a session of its own, whose group is killed when its call ends, however it ends (MCP's stdio client does this for the MCP apps, and the script dialect, FreeCAD's, now does too). A process that leaves its group, in a session of its own, would still outlive it, as the worker's own user, with every later call's files in view: a worker serves every tenant. So the worker, alone in its container (`WORKER_SWEEP=1`), kills every other process of its user after each call, before it takes the next, and empties `/tmp`; and Docker's init reaps what is killed. `RLIMIT_NPROC` isn't set: it counts a user's processes across every container that runs as that uid on the host, and the container's PID limit bounds them better.
- **Each call's limits are artifactr's** (`WORKER_LIMITS`, from `FILES_WORKER_LIMITS`, its defaults when empty): an edit's 30 s and a render's 10 s, the CLI's 30 CPU seconds, 2 GiB of address space and 256 MiB files, and a 384 MiB reply. The container's memory is above the CLI's address space with the call's `tmpfs`, which counts toward it.
- **A token for each worker,** `FILES_<APP>_TOKEN`, which `make env` generates with `openssl rand -hex 32`, into a `.env` only its owner may read, and fails without `openssl` rather than write an empty one. The application holds every app's, and a worker only its own. A worker refuses to start with none, as `worker_app` does, or with one under 32 characters, as do the application's settings. Like every setting, it is in its container's environment, which `docker inspect` shows to whoever may run Docker.

### The editors' origins

- **Each bridged app's editor is an origin of its own:** its own port on this machine's loopback, after the application's and the mini apps': `app_port` and two, three and four (`GRIDCRAFT_EDITOR_PORT`, `PDFCRAFT_EDITOR_PORT`, `CADCRAFT_EDITOR_PORT`), which the template's question keeps within 65535. `Site.editors` names them, the shim answers only `PORTAL_URL`, and the build's page may be framed only by its shim and the portal; the portal's own `frame-src` is portalr's `policy()`'s, from `Site`, so nothing here sets it. The editor sets and reads no cookie, and holds no secret. Its policy keeps the build's page to its own origin (`default-src 'self' blob:`, so `connect-src` too); the editor's container is on a network with a route out, which nothing in it uses.
- **Loopback only, by default.** `APP_BIND` publishes the editors where it publishes the application, so a LAN is opt-in, as it is for the application ([ADR-0006](0006-networks-and-published-ports.md)), and puts the editors before anyone on it.
- **`PORTAL_URL` is the portal's origin exactly.** The shim answers it alone, so `http://localhost:8800` and `http://127.0.0.1:8800` are two portals: the one people use is the one to name.
- **On a tailnet, each editor needs a port of its own,** since an origin is a host and a port: `tailscale serve --bg --https=<port> http://127.0.0.1:<editor's port>` for each, beside `make tailnet`, then `FILES_EDITORS` with each editor's tailnet address, and `PORTAL_URL` with the portal's, the only page that may frame them. `make tailnet` serves the application alone.

### The proof

`scripts/check-files [APP...]`, `moon run stackr:files`, generates an application at `HEAD`, builds the workers and editors of WordCraft, GridCraft, PdfCraft, CADCraft and FreeCAD by default, starts them with the application's own `compose.yaml`, and checks:

- each worker's posture as Docker runs it: read-only, user 10002, `[ALL]` capabilities dropped, `no-new-privileges`, its memory, CPU and process limits, no port, and the internal `files` network alone;
- that a connection to a public address and a lookup of a public name, from inside the worker, both fail;
- that its image carries its release's licences, and PdfCraft's its OCR models' attribution;
- from a probe on the `files` network, in the worker's image: a request without the token is refused; the app is the pinned version; a new file is made, read back as the app's format and, where it renders, rendered; and a zip bomb, a file past the limit and bytes of no format each end within the deadline, in a typed failure;
- that each editor is published on 127.0.0.1 alone, and serves the shim with `frame-ancestors` naming the portal.

CI's "Native files" job runs it on amd64 and arm64 runners, when stackr or a project it depends on changes.

## Options considered

### Option A: The application's Dockerfile, one target per role, built per app (chosen)

| Dimension | Assessment |
|---|---|
| Fit | One `uv.lock` for both ends of the wire; `make up` builds it with the application |
| Cost | Each worker carries the application's whole virtual environment |
| Release | Nothing to publish; a deployment builds from its own checkout |

### Option B: A thin image stackr releases, pinned by digest, as RFC-0003 first said

**Cons:** the worker's artifactr would be stackr's release's, not the application's, and the two must speak one wire; and an application pinned to a lattice commit would need an image built at that commit. It stays the right shape for the AWS recipe's tasks, which can't build: deferred to that.

### Option C: One worker serving every app, mounted by path

**Cons:** one container's limits shared by every app, and two jobs at once in it, which ADR-0013 refuses: a worker scales by containers.

### Option D: The editors on the application's own server, by `Host`, as mini apps' sandbox is

**Cons:** the builds, tens of megabytes each, in the application's image; and the application's process serving them. A static server of their own is simpler, and reaches nothing.

## Trade-off analysis

Building the worker from the application's own Dockerfile costs image size, a few hundred megabytes for each app, and buys one artifactr on both ends of the wire with nothing to release. A worker per app costs a container each, and keeps one app's hostile file from sharing another's limits.

## What is not isolated

- **The kernel.** A worker is a container on the host's kernel, under Docker's default seccomp profile, and AppArmor's where the host has it, with no gVisor or VM between it and the host.
- **The application, from the worker.** The application joins `files`, so a worker can open a connection to it there, on its own port, where every route asks for a person's token or a service's key. Workers can reach each other on `files`, where each asks for the token; the token is one for all of them.
- **Names on `files`.** Docker's embedded DNS answers the names of the containers on it; it resolves nothing outside.
- **What the token gives.** Whoever has `FILES_WORKER_TOKEN`, and a place on `files`, can have any worker read any file.
- **A crash's message.** A `crashed` failure carries the end of what the CLI printed, which a hostile file can shape; the application logs it, and must not show it to people or agents (ADR-0013).
- **The editor in the browser.** It is the app's build, as released, on its own origin, under a policy that reaches nothing; its isolation from the portal is the browser's same-origin policy.

## Consequences

- Easier: `make up FILES="wordcraft gridcraft"` in a generated application, with `make env`'s token, runs native files' routes, the agent's tools and each app's worker; with the portal, GridCraft's, PdfCraft's and CADCraft's editors too.
- Harder: each app is an image to build, from a download; a worker's first build fetches its release from GitHub.
- Not done: **an upload route.** Nothing in lattice makes a native file from an upload: `files_router` names existing artifacts, and portalr has no control for one. A generated application's files arrive through `NativeFiles.upload` in code. The route is artifactr's to add, with portalr's control after.
- Not done: **the image's digest in provenance.** `WORKER_BUILD` is unset, since only the built image knows its digest, so a revision records the app and its version, and no image.
- Not done: the images for the AWS recipe (Option B), and the editors on a single host's edge, behind TLS, on host names of their own ([files ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md)'s fourth action item).

## Action items

1. [x] `native_files` in the template, `Files` and `editor.py`, the worker's and editor's targets, the `files` network, the containers' limits, the token and `make up FILES=...`.
2. [x] The release-pin check in `scripts/check-template`.
3. [x] `scripts/check-files`, and CI's "Native files" job.
4. [ ] An upload route for a new native file, in artifactr, and portalr's control.
5. [ ] The image's digest as `WORKER_BUILD`.
6. [ ] The editors on a single host's edge, on host names of their own.
