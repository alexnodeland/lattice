# ADR-0051: Build-time fetches, bounded and tried again

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

Amends [ADR-0048](0048-grafanas-clickhouse-data-source-and-the-adoption-dashboard.md), which fetched ClickHouse's data source plugin with `ADD --checksum` as Grafana's image is built.

## Context

Three CI failures in one day came from network fetches made while building or starting the stack, and none of them was in lattice's code:

- **The plugin's `ADD --checksum` from grafana.com stalled** for about seven minutes, then failed with `stream error … INTERNAL_ERROR`. BuildKit's `ADD` has no timeout and no retry.
- **quay.io answered `503`** for prom-label-proxy's manifest while `make up` pulled the stack's images. Compose's pull, and the `up` that pulls, fail at the first such answer.
- **The files worker's resolve found no `pydantic-ai-slim==2.61.0`** on arm64, minutes after that version's release. A later run of the same commit passed. The worker's `uv pip install` resolves against the index, under `uv.lock`'s versions, and the index's copies can lag a release.

## Decision

Each of these fetches is bounded and tried again a few times, and fails loudly once it has run out of tries. No pin or checksum is weakened.

- **The plugin is fetched with curl, not `ADD`.** A stage built on the `curlimages/curl` image that `compose.yaml` pins, by digest, runs on the build platform. Each try has a 10 s connect timeout and a 120 s limit, with up to four retries (`--retry-all-errors`). The archive is checked with `sha256sum -c` against the same sha256 for each architecture that `--checksum` held. A `*)` arm refuses any architecture that has no pin. The plugin is still signed by Grafana Labs, and the image still loads it without a network.
- **`make up` pulls the pinned images first,** with `docker compose pull --ignore-buildable`. A failed pull is tried again after 20 s, then 40 s, up to three tries. After the last it stops, saying so.
- **The files worker's resolve is tried again,** after 30 s, then 60 s, up to three tries. The retries add `--refresh`, so they read the index afresh. Its versions are still `uv.lock`'s, through `--constraint`.
- **Checks hold this:**
  - `scripts/check-template` checks that the worker's stage keeps `uv export --locked`, `--constraint` and the retry.
  - It checks that the plugin's stage pins a sha256 for amd64 and arm64 alone, refuses any other architecture, and keeps the bound, the retry and `sha256sum -c`.
  - `scripts/check-make` runs `make up` against a fake `docker` whose pull fails twice and then passes, and against one whose pull fails three times.

This follows `scripts/craft`, which already fetches the crafting apps' releases with `curl --retry 5 --retry-all-errors` and checks each against its SHA-256 before anything of it is unpacked.

## Consequences

- **A fetch that is down for good still fails the build,** after its last try: about 90 s of waiting for the worker's resolve, 60 s for the pulls, and up to five bounded tries for the plugin. A resolve that is truly unsatisfiable, such as a version that was never published, also waits those 90 s before it fails.
- **Some pulls are still tried only once.** `make up` runs `clickhouse-init` and `umami-init` with `run --rm`, from profiles of their own, after the pull. `clickhouse-init`'s image is the `clickhouse` service's, so it is pulled with the analytics profile. `umami-init`'s curl image is pulled only by its own `run`.
- **The other images' builds still fetch once:** their base images, apt and the application's own `uv sync`. Only the fetches that failed are covered.

## Alternatives considered

- **Caching the plugin's archive with `actions/cache`.** The archive would have to be passed into the Grafana build as a build context. That build runs from three places: Compose, `deploy/build-images` and the release images. It would also cover only CI, not a machine that builds the stack. The bounded fetch covers both in one file, and the checksum still decides what is used.
- **BuildKit's layer cache across jobs** needs a cache backend: GitHub Actions' cache or a registry. It is a larger change to every image's build, and it hides a slow fetch rather than bounding it.
- **A registry mirror or a pull-through cache** is a service of its own to run, which lattice's CI avoids.
