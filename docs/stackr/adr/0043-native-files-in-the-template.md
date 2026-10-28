# ADR-0043: Native files in the template: a worker for each app, with no route out, and its editor on a loopback origin

**Status:** Accepted, amended by [ADR-0046](0046-native-files-a-relay-a-slimmer-worker-blender-and-the-editors-at-the-edge.md)
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

> **Amended (2026-10-28), for [issue #874](https://github.com/alexnodeland/lattice/issues/874):** FilmCraft 0.8.0 (`VideoProject`), EffectCraft 0.11.1 (`MotionGraphics`) and SoundCraft 0.8.0 (`AudioSession`), whose adapters [files ADR-0016](../../artifactr/files/adr/0016-a-project-that-holds-its-own-media-is-a-native-file.md) added, join `copier.yml`'s crafts at the versions lattice's pins name, so every type lattice keeps has a worker the agent can make and edit it in. Each runs as the others do, with the same posture, limits and no route out, and `scripts/check-files` proves each. FilmCraft and EffectCraft ran on the worker's defaults, with no `memory:` of their own: the container's `FILES_WORKER_MEMORY`, 3g, with the call's 1 GiB `tmpfs` counted inside it, and each call's address-space limit applied separately; one is declared only when a real project runs out of memory. None has an editor yet: each needs its browser build piloted through the shim first ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)), so a person downloads and uploads their files. Each is off in a workspace until an admin switches it on.

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
- **Nothing outlives a call.** A CLI starts in a session of its own, whose group is killed when its call ends, however it ends (MCP's stdio client does this for the MCP apps, and the script dialect, FreeCAD's, now does too). A process that leaves its group, in a session of its own, would still outlive it, as the worker's own user, with every later call's files in view: a worker serves every tenant. So the worker, alone in its container (`WORKER_SWEEP=1`), sweeps after each call, before it takes the next: it kills every other process of its user, listing them again until a listing finds none new, ten times at most, so strays that start each other again are killed again; and it empties `/tmp`, opening to its owner any directory a call sealed (mode 000) so what is in it goes too. Docker's init reaps what is killed. A sweep that can't finish, strays still starting after ten listings or anything left in `/tmp`, fails the call as `crashed`, and the worker then answers every request, its health check's too, with 503, until it is restarted: it serves no other call. `RLIMIT_NPROC` isn't set: it counts a user's processes across every container that runs as that uid on the host, and the container's PID limit bounds them better.
- **Each call's limits are artifactr's** (`WORKER_LIMITS`, from `FILES_WORKER_LIMITS`, its defaults when empty): an edit's 30 s and a render's 10 s, the CLI's 30 CPU seconds, 2 GiB of address space and 256 MiB files, and a 384 MiB reply. The container's memory is above the CLI's address space with the call's `tmpfs`, which counts toward it.
- **A token for each worker,** `FILES_<APP>_TOKEN`, which `make env` generates with `openssl rand -hex 32`, into a `.env` only its owner may read, and fails without `openssl` rather than write an empty one. The application holds every app's, and a worker only its own. A worker refuses to start with none, as `worker_app` does, or with one under 32 characters, as do the application's settings. Like every setting, it is in its container's environment, which `docker inspect` shows to whoever may run Docker.

### The editors' origins

- **Each bridged app's editor is an origin of its own:** its own port on this machine's loopback, after the application's and the mini apps': `app_port` and two, three and four (`GRIDCRAFT_EDITOR_PORT`, `PDFCRAFT_EDITOR_PORT`, `CADCRAFT_EDITOR_PORT`), which the template's question keeps within 65535. `Site.editors` names them, the shim answers only `PORTAL_URL`, and the build's page may be framed only by its shim and the portal; the portal's own `frame-src` is portalr's `policy()`'s, from `Site`, so nothing here sets it. The editor sets and reads no cookie, and holds no secret. Its policy keeps the build's page to its own origin (`default-src 'self' blob:`, so `connect-src` too); the editor's container is on a network with a route out, which nothing in it uses.
- **Loopback only, by default.** `APP_BIND` publishes the editors where it publishes the application, so a LAN is opt-in, as it is for the application ([ADR-0006](0006-networks-and-published-ports.md)), and puts the editors before anyone on it.
- **`PORTAL_URL` is the portal's origin exactly.** The shim answers it alone, so `http://localhost:8800` and `http://127.0.0.1:8800` are two portals: the one people use is the one to name.
- **On a tailnet, each editor needs a port of its own,** since an origin is a host and a port: `tailscale serve --bg --https=<port> http://127.0.0.1:<editor's port>` for each, beside `make tailnet`, then `FILES_EDITORS` with each editor's tailnet address, and `PORTAL_URL` with the portal's, the only page that may frame them. `make tailnet` serves the application alone.

> **Amended (2026-10-26):** WordCraft 0.11.0 has the `?host=parent` bridge ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)), so it has an editor too, `WORDCRAFT_EDITOR_PORT`, at `app_port` and five: four editors, and the next five ports after the application's are the mini apps' and the editors', so `app_port` is at most 65530. The editors at the edge are four, and `wordcraft.<domain>` is served by the same rule.

> **Amended (2026-10-27) by [portalr ADR-0084](../../portalr/adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md):** on a tailnet, `make tailnet` serves each running editor's port itself, and writes `PORTAL_EXTRA_URLS`, the portal's other origin, so `PORTAL_URL` stays `http://127.0.0.1:<app_port>` and `FILES_EDITORS` stays empty. Each editor's shim and `frame-ancestors` name every portal origin (`PORTAL_URL` and `PORTAL_EXTRA_URLS`, which compose.yaml passes to each editor), and `config.json` names the editors beside each other origin, on the ports they have here. An editor with no port of its own, at the edge, can't be beside another origin: the application refuses to start with both, and says why.

### The proof

`scripts/check-files [APP...]`, `moon run stackr:files`, generates an application at `HEAD`, builds the workers of every app a worker runs, and the editors of the four bridged ones, starts them with the application's own `compose.yaml`, and checks, for each:

- **Its posture as Docker reports it, value by value against what `compose.yaml` configures:** read-only; user 10002; not privileged; no capability added and all dropped; `no-new-privileges` and no other security option, so seccomp and AppArmor are Docker's defaults; an init; 3 GiB of memory and as much with swap; 2 CPUs; 128 processes; the host's PID namespace not shared; no mount and no device; `/tmp` a 1 GiB `tmpfs` with `noexec,nosuid,nodev`; and its own network alone, internal, made with no address for the host on it, with no port published. Each editor's the same way, as user 10003, 256 MiB and 64 processes, on `editors`, published on 127.0.0.1 alone.
- **That it reaches nothing outside its network,** from inside it: `github.com` and `host.docker.internal` don't resolve; TCP to 1.1.1.1:443, TCP to [2606:4700:4700::1111]:443, UDP DNS to 1.1.1.1:53 and TCP to 169.254.169.254:80 each fail. The check takes any error as a failure to reach; each run so far, locally and on CI, has printed `Network is unreachable` for all four. That the host has no address on the network is Docker's configuration (`inhibit_ipv4`), which the check reads back; it also connects to where the host's address would be (Docker's gateway, or else the subnet's first address) and fails on an answer, but with the option on, that address is the worker's own, so the attempt is passed over. `inhibit_ipv4` needs a Docker Engine whose bridge driver honours it; the check prints the Engine it ran on (29 locally, and the GitHub runners'). ICMP can't be tried, since the worker has no `CAP_NET_RAW`.
- **From a probe on its network, in its image:**
  - the release's licence files, and each notice `CRAFTS` declares, PdfCraft's OCR models' attribution and licences among them, are in the image;
  - a request without its token is refused;
  - the worker runs the app at its pinned version;
  - a new file is made, read back as the app's format, and rendered (FreeCAD and FigCraft are given a shape first, FilmCraft a sequence and EffectCraft a composition, each with a title);
  - a zip whose one part inflates to 1 GiB, a file past the 256 MiB limit and bytes of no format each end within the deadline, in a typed failure. The zip is a bomb to an app whose files are zips; one whose files aren't (PDF, DXF, PSD, SVG, FreeCAD's) refuses it at its first bytes, so for those it shows only that refusal, and their own hostile files are each app's corpus's ([files ADR-0011](../../artifactr/files/adr/0011-a-gate-for-each-app.md)'s second action item).
- **That nothing outlives a call:** a `sleep` its user started in a session of its own, a file in `/tmp` and a directory sealed with mode 000 holding a file, each seen there before the probe's calls, are gone after them.
- **Each editor's shim** has `frame-ancestors` naming the portal it was given.

The probe container, in the worker's image, stands in for the application: the generated application's own container is not run against a worker here. The application's side, `Files` over `Worker`, is the generated tests', over the worker in process.

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

**Cons:** the builds, tens of megabytes each, in the application's image; and the application's process serving them. A static server of their own is simpler, and holds nothing.

### Option E: One network and one token for every worker

**Cons:** a worker that runs code could call its siblings, some of them trusting the worker for their confinement, with hostile input of its own. A network and a token for each cost a line of `.env` each.

## Trade-off analysis

Building the worker from the application's own Dockerfile costs image size, a few hundred megabytes for each app, and buys one artifactr on both ends of the wire with nothing to release. A worker per app, each on its own network with its own token, costs a container, a network and a token each, and keeps one app's hostile file from sharing another's limits or reaching another's worker.

## What is not isolated

- **The kernel.** A worker is a container on the host's kernel, under Docker's default seccomp profile, and AppArmor's where the host has it, with no gVisor or VM between it and the host.
- **The application, from a worker.** The application joins each worker's network, so a worker can open a connection to the application's own port there. Most of its routes ask for a person's token or a service's key, but not all: `/healthz`, the portal's `config.json` and UIs, its sign-in passthrough (`/auth/v1/token`, `/auth/v1/user`, `/auth/v1/logout`, which pass a password or a refresh token on to Supabase Auth, as from a browser), and the mini apps' sandbox origin answer anyone who reaches them. A worker that runs code could make those calls, from inside the deployment, as any visitor to the application could from outside it. A relay as the only member of both networks would close it, and isn't built.
- **One call from the next, within a worker.** Every tenant's calls go to the same worker. What the sweep removes after each call is its user's processes and `/tmp`; a process started as another user (none can be: no capabilities, no new privileges) or state the CLI keeps in memory across calls (none does: a CLI is started for each call) is outside it. Between the CLI's end and the sweep, a process that left the CLI's session could run alongside the worker for the rest of that call.
- **The token in the environment.** Each worker's token, like every setting, is in its container's environment, which `docker inspect` and `docker compose config` show to whoever may run Docker. A worker holds only its own; the application holds every one. A CLI runs as the worker's user, so code a hostile file runs in it can read the worker's environment from `/proc`, and so that worker's own token: which gives it nothing it hasn't, its own worker.
- **The health check, during a sweep.** The health check's process runs as the worker's user, so a sweep that runs while it does kills it: one failed check, which the next passes.
- **What a token gives.** Whoever holds an app's token, and a place on its network, can have its worker read files they send it. A worker keeps no file, so a token gives no stored file, only the worker's work.
- **Names.** Docker's embedded DNS answers the names of the containers on a worker's network, the application's among them; it resolves nothing outside.
- **A crash's message.** A `crashed` failure carries the end of what the CLI printed, which a hostile file can shape; the application logs it, and must not show it to people or agents (ADR-0013).
- **The editor.** It is the app's build, as released, on its own origin, under a policy that keeps it to that origin; its isolation from the portal is the browser's same-origin policy. Its container holds no secret, and its network has a route out, which nothing in it uses.
- **The worker's virtual environment** is the application's, whole: its code and every library it installs, in each worker, which a slimmer one, `artifactr-ai[files]` alone, would cut. It runs none of it but artifactr's worker.

## Consequences

- Easier: `make up FILES="wordcraft gridcraft"` in a generated application, with `make env`'s tokens, runs native files' routes, the agent's tools and each app's worker; with the portal, GridCraft's, PdfCraft's, CADCraft's and (since 0.11.0) WordCraft's editors too.
- Harder: each app is an image to build, from a download; a worker's first build fetches its release from GitHub.
- Not done: **an upload route.** Nothing in lattice makes a native file from an upload: `files_router` names existing artifacts, and portalr has no control for one. A generated application's files arrive through `NativeFiles.upload` in code. The route is artifactr's to add, with portalr's control after.
- Not done: **Blender** ([files ADR-0015](../../artifactr/files/adr/0015-blender-on-the-script-dialect-and-no-file-that-may-run-python.md)). The worker runs it (`WORKER_APP=blender`), but the template builds no image for it: its release is x86_64 only, its CLI needs 4 GiB of address space, which a worker's `FILES_WORKER_LIMITS` and memory must both be raised above, and its GPL-3.0 notices and source offer must travel with it. Each is its own work.
- Not done: **the image's digest in provenance.** `WORKER_BUILD` is unset, since only the built image knows its digest, so a revision records the app and its version, and no image.
- Not done: the images for the AWS recipe (Option B), and the editors on a single host's edge, behind TLS, on host names of their own ([files ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md)'s fourth action item).

## Action items

1. [x] `native_files` in the template, `Files` and `editor.py`, the worker's and editor's targets, a network and a token for each worker, the containers' limits, the sweep after each call, and `make up FILES=...`.
2. [x] The release-pin check in `scripts/check-template`.
3. [x] `scripts/check-files`, and CI's "Native files" job.
4. [x] An upload route for a new native file, in artifactr, and portalr's control.
5. [x] The image's digest as `WORKER_BUILD`.
6. [x] The editors on a single host's edge, on host names of their own.
7. [x] A relay between the application and the workers, so no worker reaches the application's unauthenticated routes.
8. [x] A slimmer worker image: `artifactr-ai[files]` alone, at the application's lock.
9. [x] Blender's worker in the template: an x86_64-only image, its 4 GiB floor in the limits and the container's memory, and its GPL notices and source offer.
