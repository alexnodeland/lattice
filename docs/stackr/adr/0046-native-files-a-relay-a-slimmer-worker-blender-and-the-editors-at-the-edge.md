# ADR-0046: Native files: a relay, a slimmer worker, Blender, and the editors at the edge

**Status:** Accepted
**Date:** 2026-10-22
**Deciders:** Alex Nodeland

Amends [ADR-0043](0043-native-files-in-the-template.md). It closes ADR-0043's action items 5 to 9, and native files' [ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md) and [ADR-0015](../../artifactr/files/adr/0015-blender-on-the-script-dialect-and-no-file-that-may-run-python.md) stackr's items.

## Context

ADR-0043 put each crafting app's worker on a network of its own, which the application joined, and left five things undone:

- **The application, from a worker.** The application joined each worker's network, so a worker could reach the application's port there. A worker running code a hostile file brought could call the routes that answer anyone: `/healthz`, the portal's `config.json`, its sign-in passthrough, and the mini apps' origin.
- **The worker's virtual environment was the application's whole,** in every worker: hundreds of megabytes of code it never runs.
- **`WORKER_BUILD` was unset,** so a revision's provenance recorded the app and its version, but no image.
- **Blender had no image.** The worker runs it, but its release is x86_64 alone, its CLI needs 4 GiB of address space, and its licence, the GPL-3.0, asks for its source to be offered with it.
- **The editors had no place on a single host.** The host overlay gave the application the `stackr` network alone, so it reached no worker. The editors published on the host's loopback, where no browser reaches them.

## Decision

### A relay for each worker

- **The worker is `files-<app>-worker`, and its relay is `files-<app>`,** the name the application already calls. The relay is socat, pinned by digest, which passes each connection on to its worker and does nothing else. It runs read-only, as user 10004, with no capabilities, 64 MiB and 32 processes.
- **Two networks, each internal.** The worker's `files-<app>` holds the worker and its relay alone. `files` holds the application and every relay. The application leaves the workers' networks.
- **A worker can reach its relay, which reaches only the worker,** and never the application. A relay on `files` can reach the others there. It runs no code a file brings, and none of those relays reaches anything but its own worker.

### A slimmer worker

- **The worker's environment is `artifactr-ai[files]` alone,** at the versions `uv.lock` pins. A stage of its own exports the lock as constraints and installs the files extra into `/opt/worker`. The worker and the application still install one artifactr, from one lock. In a generated application that was 55 MB, against the application's whole environment.

### `WORKER_BUILD`

- **`make up` builds first, then tells each worker the ID of the image it runs in,** as `FILES_<APP>_BUILD`, which compose passes on as `WORKER_BUILD`. This is the local image's ID, `sha256:...`, not a registry digest: an image can't hold its own digest, and a generated application publishes no worker image. A deployment that runs `docker compose` directly, not `make up`, leaves it unset, as before.

### Blender

- **`blender` joins `copier.yml`'s crafts,** at 5.2.2, the version lattice's pin names, as `Scene`. Its pin is lattice's own, and `scripts/check-template` holds it to that. An app's entry may now also name:
  - **`platform`:** Blender's `linux/amd64`, the only platform its worker builds and runs for. Elsewhere Docker runs it emulated, and `scripts/check-files` passes it over unless it is named.
  - **`memory`:** the GiB its CLI needs, 4. Its calls' limits default to that address space (`FILES_BLENDER_LIMITS`), and its container to 2 GiB more (`FILES_BLENDER_MEMORY`), for the call's `tmpfs` and the worker.
  - **`packages`:** the X11 and GL libraries its tarball links, and Mesa, which draws its pages with no GPU. The worker's stage installs them, for this app alone.
  - **`source`:** where its release's source is. The image holds `/opt/craft/SOURCE-OFFER`, which names the release and that address, beside the tarball's own `license/` folder and `copyright.txt`.
- **The image holds Blender unmodified,** as its release was published. An operator who conveys the image to others conveys Blender under the GPL-3.0, and the offer travels with it.

### The editors at a single host's edge

- **Each at `https://<app>.<domain>/`.** The host overlay puts each editor on the `stackr` network, with no port, and `PORTAL_URL` at `https://app.<domain>`, the only page that may frame it. It tells the application `FILES_EDITOR_DOMAIN`, from which each editor's address is made, unless `FILES_EDITORS` says otherwise. The application joins `files` there too, so it reaches its workers on a host as it does locally.
- **stackr's Caddy serves the names `STACKR_EDITOR_HOSTS` lists,** such as `gridcraft.example.com, pdfcraft.example.com`, each passed by its first label to `files-<app>-editor:8000`, for the apps with an editor, the three then and WordCraft since ([stackr ADR-0043](0043-native-files-in-the-template.md)'s amendment). Anything else is 404. Only the listed names are served, so a certificate is asked for each only when its app runs. With none listed, `editors.localhost` stands in, which Caddy's own CA signs.

## Options considered

### For the relay

| | One relay for each worker (chosen) | One relay for every worker | A relay in the application's image, in Python |
|---|---|---|---|
| A worker reaches | Only itself, through its relay | Every other worker, through the relay | Only itself |
| Code to keep | None: socat, pinned | None | A proxy of our own |
| Cost | A small container for each app | One container | A container for each app, and the application's image |

One relay for every worker would join every worker's network. A worker reaching it would reach the others' ports through it, which ADR-0043's Option E refused.

### For `WORKER_BUILD`

- **A digest from a registry:** none exists for a worker built locally, and building and pushing one is the AWS recipe's work (ADR-0043's Option B).
- **A build argument, the lattice commit and the app's version:** it describes the inputs, not the image. The image's ID is what Docker ran.

### For the editors on a host

- **The editors on stackr's Caddy by a wildcard name, `*.<domain>`:** a wildcard certificate needs the DNS challenge, and a DNS provider's token on the host.
- **Caddy joins the application's `editors` network:** stackr's Caddy would need a network that only the application's Compose project makes, so the stack couldn't start before the application.

## Trade-off analysis

A relay for each worker costs one small container for each app. It buys what ADR-0043 couldn't: a worker running hostile code reaches nothing of the application. The slimmer environment costs a stage, and keeps one lock. The editors' names cost a line of stackr's `.env` and a DNS record each, and no wildcard.

## What is still not isolated

- **The relays, from each other.** They share `files` with the application. A relay runs nothing but socat, and none reaches more than its own worker.
- **The editors, on a host,** are on the `stackr` network, as the application is, and could reach its services. An editor runs lattice's own static server and holds no secret. Nothing in it runs code a file brings.
- **A relay's connections** are at most 16 at once (`max-children=16`), shared by every tenant of its app, with no timeout for an idle one. Each tenant's share of its worker is bounded upstream, by its readings, which pages take too since files ADR-0018 (lattice#565).
- **What floats.** The base images are pinned by tag, and the worker's apt packages, Blender's libraries and Mesa among them, by name, as the template's images already are. `WORKER_BUILD` is the local image's ID, not a registry digest.
- Everything else in ADR-0043's list stands, except "The application, from a worker", which the relay closes.

## The source offer's limits

- **Blender's source** is named by one address, download.blender.org's tarball of exactly 5.2.2, and its SHA-256, `56a3b1ec97479ff24dce65d2f09f8a1895005cece279b701fe4fcf74bce3f77e`, which we took from it on 2026-10-22. Blender publishes only its MD5, `8fcb442090c29a4f12652dcd9d6ae1f8`, which matched. The offer points to that copy. It is not the written offer, good for three years, that GPL-3.0's section 6(b) describes: an operator who conveys the image to others and can't rely on that copy staying up gives one, or the source with it.
- **The Debian packages** the image installs for Blender (X11, GL, Mesa) carry their own copyright files in `/usr/share/doc`, as Debian ships them. No source offer is written for them. Their source is Debian's, at the trixie versions installed, which an operator who conveys the image answers for as for any Debian-based image.
- **The Caddyfile's editors** are the apps with an editor in `copier.yml`. `scripts/check-template` holds the two to each other, so a new app's editor is never a silent 404 at the edge.

## Consequences

- Easier: a worker reaches no route of the application's. A worker's image carries only what it runs. A revision records the image its worker ran in. Blender runs in the template. A single host serves the editors.
- Harder: a running app is three containers with its editor, and two networks. Blender's worker is x86_64 alone, so on an arm64 machine it runs emulated, slowly, if Docker emulates at all. Its first build downloads its tarball, about 400 MB.
- To revisit: an image the AWS recipe can run, with a registry digest; Blender's measured memory under a hostile allowed scene (files ADR-0015).

## Action items

1. [x] The relays and the `files` network, and `scripts/check-files`' checks of them.
2. [x] The worker's own environment, `/opt/worker`.
3. [x] `WORKER_BUILD` from `make up`.
4. [x] Blender's worker: `platform`, `memory`, `packages` and `source` in `copier.yml`'s crafts.
5. [x] The editors at a single host's edge: the host overlay, `FILES_EDITOR_DOMAIN` and `STACKR_EDITOR_HOSTS`.
6. [ ] Blender's worker through `scripts/check-files` on x86_64, which CI's "Native files (amd64)" job runs.
