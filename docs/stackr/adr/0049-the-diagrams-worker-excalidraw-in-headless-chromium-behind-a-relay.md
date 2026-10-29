# ADR-0049: The diagrams worker: Excalidraw in headless Chromium, behind a relay

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Records stackr's half of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 2: the worker that artifactr's converter calls ([artifactr ADR-0091](../../artifactr/adr/0090-diagrams-drawn-by-the-agent-through-a-converter.md)). It is the worker [artifactr ADR-0088](../../artifactr/adr/0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md) measured, and it is built and isolated as native files' workers are ([ADR-0043](0043-native-files-in-the-template.md), [ADR-0046](0046-native-files-a-relay-a-slimmer-worker-blender-and-the-editors-at-the-edge.md)).

## Context

- **artifactr draws through a port,** `Converter`, with three calls: Mermaid to elements, skeletons to elements, and a diagram rendered as SVG or PNG. `WorkerConverter` calls them over HTTP, with a token, and holds every reply to limits and checks (ADR-0091). Nothing answered it.
- **Only Excalidraw's own code draws as Excalidraw does.** `parseMermaidToExcalidraw`, `convertToExcalidrawElements` and `exportToSvg` are browser code. ADR-0088 measured them in headless Chromium and in jsdom with resvg, and chose Chromium: its PNGs are right, and it is faster at the 2,000-element limit.
- **Font subsetting needs `'unsafe-eval'`.** Without it, an export embeds whole faces: an SVG of 299 kB against 15 kB. The portal's policy never allows it (ADR-0088), so a small export is the worker's.
- **Xiaolai, Excalidraw's CJK face, stays out of the worker's image** until its author answers (lattice#679): it is OFL 1.1, but its README reserves the names Xiaolai and Kose, and Excalidraw's modified copy keeps the name. Without a CJK face, Chromium draws tofu.

## Decision

### The worker

- **A Node service, `packages/stackr/workers/diagrams`,** in lattice's Bun workspace, so `bun.lock` pins everything it runs and ships.
  - Its server drives **one warm headless Chromium** through Playwright's driver, `playwright-core`.
  - Chromium loads its **page**: Excalidraw 0.18.1 and `@excalidraw/mermaid-to-excalidraw` 2.2.2, the version Excalidraw itself depends on, built by Vite.
- **It answers `WorkerConverter`'s contract** and nothing else:
  - `POST /mermaid`, `POST /skeletons` and `POST /render`, each with the worker's token;
  - `GET /healthz`, which says only Excalidraw's version, for Compose's health check;
  - a failure as a 4xx or a 5xx with `{reason, message}`.
- **One job at a time, within its deadline,** at most 10 s whatever a call asks for.
  - A job that waits past its deadline isn't started.
  - A job that runs past it is answered `timeout`. A job the page didn't answer, because the page or the browser failed, is answered `crashed`, in fixed words. After either, the page is thrown away, and a new one is made at once, in the background, so the next job finds it warm unless it comes within the few seconds a cold page takes. A browser that died is started again.
  - **`invalid` is the page's own refusal alone:** Mermaid that doesn't parse, or skeletons Excalidraw can't convert, which the page answers with, in their words. Such a job, and a `too_large` one, leaves the page as it was.
  - The page is made at most once at a time: a job that gives up waiting for a cold page leaves no second one being made behind it.
- **Its replies are what artifactr checks for** (ADR-0091). Running the real worker's replies through artifactr's own `Converted` and `checked()` found four things, each fixed in the worker; artifactr needed no change:
  - **Mermaid names its nodes as it likes,** `中文` among them, and Excalidraw keeps the names as element ids. A Mermaid diagram's ids are made new, as the canvas's are. The agent's skeletons keep the ids it gave them, which artifactr holds to `[A-Za-z0-9_-]`.
  - **A Mermaid `click` gives an element a link,** which an export draws as `<a href>`. Converted elements keep no link.
  - **Mermaid's pictures are SVGs,** such as a Gantt chart's, with `foreignObject` and styles of their own. Each is drawn once, on a canvas in the page, and kept as a PNG.
  - **An export names esm.sh** for a face it couldn't embed, Xiaolai while the worker has none. Such a `@font-face` is dropped, and the viewer's own face draws those words. An SVG names no address outside itself.
- **The PNG is the SVG, drawn.** Excalidraw's own PNG export draws with the faces the document loaded, which the page doesn't, so it fell back to a serif. Drawing the exported SVG gives the PNG the same embedded faces.
- **A diagram is restored before it renders.** `restoreElements` fills what an element leaves out with Excalidraw's defaults, as the canvas does.

### The page, and `'unsafe-eval'`

- **The page's origin is `http://diagrams.invalid`,** which no network has. The server answers every request to it from the page's own files, through Playwright's routing, and refuses any other request, logging each origin once.
  - Playwright's routing sees the page's HTTP requests, not a WebSocket's or WebRTC's. Those the policy refuses (`connect-src` names no other origin), and the container has no route out: each wall stands without the others.
- **Its policy is the only one in lattice with `'unsafe-eval'`:**

  ```text
  default-src 'none'; script-src 'self' 'unsafe-eval'; worker-src 'self' blob:;
  style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: blob:;
  connect-src 'self' data: blob:; base-uri 'none'; form-action 'none'
  ```

- **`'unsafe-eval'` is there for font subsetting alone.** The page runs Excalidraw's and Mermaid's code, and nothing the model wrote. What the model sends is data: Mermaid's source, skeletons and diagrams. Mermaid parses its source; it never runs it as code.
- **The worker's container has no route out** either (below): the policy and the routing are a second wall, not the only one.

### The image

- **`diagrams-worker`, a target of the template's Dockerfile,** in two stages.
  - **`diagrams-build`** is the Bun lattice uses, pinned by digest. `scripts/build-diagrams-worker.sh` clones lattice at the commit `uv.lock` pins artifactr at, so the worker and the converter that calls it come from one commit. It runs `bun install --frozen-lockfile` and builds the page and the server.
  - **`diagrams-worker`** is Playwright's image, `mcr.microsoft.com/playwright:v1.64.0-noble`, pinned by digest. Its Chromium is the one Playwright 1.64.0 drives, and the worker's `playwright-core` is 1.64.0.
- **It runs as user 10005,** with `HOME` in its tmpfs.
- **Noto CJK draws CJK.** The image installs Debian's `fonts-noto-cjk` (SIL OFL 1.1), and removes the image's other CJK faces, WenQuanYi Zen Hei and IPAGothic, so Noto is the one it draws with. Xiaolai is left out of the page's faces unless the build argument `XIAOLAI` is 1, which `.env`'s `DIAGRAMS_XIAOLAI=1` sets, and which waits for its author's answer (lattice#679).
- **The build checks its Playwright.** The worker's `playwright-core` comes from the lattice commit `uv.lock` pins; the image's Chromium, from the template. The Dockerfile's `ARG PLAYWRIGHT` names the image's version, and the build fails, saying so, if the worker it built drives another: an application whose libraries and template were updated apart can't run a Chromium its driver doesn't know.
- **The commit must hold the worker.** An application whose `uv.lock` pins artifactr at a commit before this record's has no `packages/stackr/workers/diagrams` to build, and the build says to update the libraries. Generated from the template once this record is in lattice, an application's lock pins a commit that has it.
- **Its notices are beside its page:**
  - `THIRD-PARTY-NOTICES.txt`, which portalr's notices plugin writes from the page's bundle, under a policy of the worker's own (`policy.json`);
  - `FONTS.txt`, with the faces' licences: the OFL's text and Noto CJK's copyright, as Debian records them.
- **About 1 GB:** Playwright's image, which carries Firefox and WebKit too, which the worker never runs.

### In the template

- **A question, `diagrams`,** default yes, asked with native files: a conversion's images are kept in native files' store.
- **The worker runs only with `DIAGRAMS=on`,** in `.env` or `make up DIAGRAMS=on`, in a Compose profile of its own, `diagrams`. `make env` generates its token, `DIAGRAMS_TOKEN`. `make up` tells it the ID of its image, as `WORKER_BUILD`.
- **ADR-0046's relay pattern.**
  - The worker, `diagrams-worker`, is alone on its network, `diagrams`. That network is internal, with no address for the host (`inhibit_ipv4`).
  - Its relay, `diagrams`, is socat. It is on `diagrams` and on `files`, where the application reaches it.
- **The container is a native file's worker's,** with its own limits:
  - read-only, no capabilities, no new privileges, under an init;
  - 1 GiB of memory and no swap (`DIAGRAMS_MEMORY`);
  - one CPU (`DIAGRAMS_CPUS`);
  - 256 processes, for Chromium's;
  - a 256 MiB tmpfs that runs nothing.
- **The application's side.**
  - `Files` registers `Diagram`, its checks and its integration key, `excalidraw`, whether the worker runs or not, so diagrams already made stay readable.
  - With `DIAGRAMS=on`, it gives the agent `diagram_tools`, over a `WorkerConverter` at `http://diagrams:8080`, with native files' store as `blobs`.
  - Native files' collection is told about diagrams (`naming=(Diagram,)`), so it keeps their images (ADR-0091).
  - The tools are offered only where `excalidraw` is on, and it is off in every workspace until switched on (lattice-core's `KNOWN`).
- **Diagrams without forms.** The template's `diagrams` doesn't need its `ui`: the application gates every artifact by its integration either way (`integration_gate(integrations, files.key_of)`), so `excalidraw` is a switch in both.

### One Excalidraw

- **`versions.env` names it: `EXCALIDRAW_VERSION=0.18.1`.** `scripts/check-template` holds these to one another:
  - the worker's `@excalidraw/excalidraw` to that version;
  - its `@excalidraw/mermaid-to-excalidraw` to the version Excalidraw depends on, read from `bun.lock`;
  - the Dockerfile's Playwright image to the worker's `playwright-core`.
- **portalr's half of the check comes with the canvas** (phase 3). Any of portalr's UIs that depends on `@excalidraw/excalidraw` is already held to the same version.

## Options considered

### For the image

| | Playwright's image, by digest (chosen) | A slim Node image, and `playwright install --with-deps chromium` | Chromium from Debian |
|---|---|---|---|
| Size | About 1 GB, with two browsers it never runs | About 600 MB | Smaller still |
| What pins Chromium | The image's digest | Playwright's version, then a download from Playwright's CDN at build time, with no digest | Debian's version, not the one Playwright drives |
| Its system libraries | Playwright's own list, tested | The same list, installed at build | Debian's |

A download with no digest would be the only part of the image not pinned by one. Chromium from Debian would differ from the one Playwright 1.64.0 is tested against.

### For where the worker's code lives

- **In stackr, in lattice's Bun workspace (chosen):** one lock, scanned by osv-scanner with the rest; Biome, TypeScript and knip check it in CI's Check job.
- **In the template, as files copied into each application:** each application would carry Excalidraw's tree and a lock of its own, which no lattice check would see.
- **In a repository of its own:** a second release to keep in step with artifactr's converter, which a commit pinned in `uv.lock` keeps in step for free.

### For where `'unsafe-eval'` lives

- **The worker's page alone (chosen):** the page runs no code the model wrote, and has no route out.
- **The portal's policy:** every page of the application would allow it, for an export that the worker makes smaller anyway (ADR-0088).

## Trade-off analysis

The worker costs an image of about 1 GB and 1 GiB while it runs, for exports that are Excalidraw's own, faces and all, and PNGs the agent can see. ADR-0046's relay costs one small container, and buys what it bought native files: a worker that reaches nothing of the application. Building the worker from the commit artifactr is pinned at costs a clone of lattice at build time, as portalr's UIs already do. It keeps the worker and its client one revision.

## What is still not isolated

- **Chromium's own sandbox is off,** as Playwright launches it by default: the container is the boundary. The page runs only Excalidraw's and Mermaid's code, on data.
- **One page serves every tenant's jobs,** one at a time, and is thrown away only after one fails or runs out of time. A job leaves no diagram in the page's document. Excalidraw's caches, of faces and of the shapes it has drawn, outlive a job.
- **With diagrams on and no native file's app running,** no `NativeFiles` exists, so nothing collects the store: the images of a drawing that was never accepted stay in it.
- **`/healthz` answers without the token,** with Excalidraw's version and nothing else, on the worker's own network.
- **The relay** takes at most 16 connections at once, shared by every tenant, as native files' do. The worker runs one job at a time, so a burst queues, each job within its own deadline. No tenant has a share of its own yet (ADR-0088).
- **What floats.** The images are pinned by digest. Noto CJK, and the packages it pulls, float with Ubuntu's archive, as the template's other apt packages do.
- **Licences** (amended 2026-10-24, lattice#679): each face's is read from its pinned upstream, and `FONTS.txt` carries the notices and pins. Liberation Sans is Liberation 2.1.5 (SIL OFL 1.1), copied over Excalidraw's 1.05, whose name table refers to Ascender's licence agreement. Not verified:
  - Excalifont, which has no standalone licence file upstream, only its name table's text in Excalidraw's source;
  - whether Excalidraw's modified Xiaolai may keep the name its author reserves, which keeps it out;
  - the WebAssembly modules subsetting runs: harfbuzz and woff2.

## Measured

On the scoped stack, with the image from this record on Docker Desktop's Linux VM, Apple silicon, through the relay:

| | |
|---|---|
| An agent's two drawings from Mermaid, a flowchart with CJK words and a Gantt chart, proposed | 4.2 s, the Gantt chart one PNG of about 8 kB |
| 2,000 elements, SVG / PNG | 1.28 s / 1.32 s |
| A 2,000-element PNG with a 0.3 s deadline | `timeout` after 0.72 s; the next job, on a new page, 5.7 s |
| Memory after those jobs | 586 MiB of 1 GiB; not killed, not restarted |

## Consequences

- Easier: the agent draws in Excalidraw's own shapes, and sees its drawing as a PNG. An export is small, and names nothing outside itself. One version of Excalidraw draws in the worker and, with phase 3, in the canvas.
- Harder: a running application with diagrams is two more containers, and an image of about 1 GB, whose first build clones lattice. Upgrading Excalidraw means re-running ADR-0088's method, with `versions.env`, the worker and the canvas moved together.
- Harder: Renovate bumps `@excalidraw/*` and `playwright-core` in the worker's `package.json` alone, and `scripts/check-template` then fails until `versions.env`, and the Dockerfile's Playwright tag and digest, move with them, as `.prototools` and the portal's Bun do.
- To revisit:
  - a per-tenant share of the worker;
  - a slimmer image, once Playwright publishes one with Chromium alone.

## Action items

1. [x] The worker, its page and its server, in lattice's Bun workspace.
2. [x] The template's `diagrams` question, the image's targets, the relay and the profile.
3. [x] `scripts/check-template`'s pins, and `scripts/check-files`' posture, egress and probe of the worker.
4. [ ] Xiaolai, behind `XIAOLAI=1`, once its author answers lattice#679.
5. [ ] portalr's canvas, held to `EXCALIDRAW_VERSION` (phase 3).
6. [ ] The tombstone sweep, run on a schedule by the application (artifactr ADR-0091).
