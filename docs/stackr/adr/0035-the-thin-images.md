# ADR-0035: The thin images

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

Builds the first part of the thin images of [RFC-0004](../rfcs/0004-hosting-recipes.md)'s phase 3: the six that carry a service's configuration, for the settings [ADR-0034](0034-the-stack-on-aws.md) gives them. `stackr-db-init` and `stackr-auth-keys` follow in their own pull request, and the release that publishes the images after them.

## Context

Fargate can't mount a checkout, so each service on Fargate whose configuration stackr owns runs a thin image: the upstream image `compose.yaml` pins, with stackr's files in it. RFC-0004 asks for one file per service, which reads from the environment whatever differs on AWS. ADR-0034 named those settings: each service's peers by their names in `stackr.internal`, and the telemetry stores' storage in S3.

Building the images settled the rest: where they're built from, how each tool takes its settings, and how CI shows that each one works on two architectures, since Fargate runs arm64 and tier 2's Floci runs the runners' amd64.

## Decision

- **Six images now:** `stackr-otel-collector`, `stackr-tempo`, `stackr-loki`, `stackr-pyroscope`, `stackr-grafana` and `stackr-litellm`. Each is the image `compose.yaml` pins, with stackr's configuration copied in, and its command set to read it.
- **Each Dockerfile is beside its configuration,** as `deploy/<service>/Dockerfile`, built from lattice's root, since Grafana's carries artifactr's and reflexr's dashboards. Each has its own `Dockerfile.dockerignore`, which lets in its files alone, as lattice's other images do.
- **The bases are `compose.yaml`'s.** `scripts/check-config aws` fails when a Dockerfile's `FROM` isn't an image `compose.yaml` pins, so Renovate's moves of the two stay together.
- **One file per service, as RFC-0004 asks.** It reads the AWS recipe's settings from the environment, with one machine's values by default, so Compose mounts the same file and changes nothing else:
  - the Collector reads `${env:TEMPO_ADDRESS:-tempo}` and its other peers so;
  - Tempo, Loki and Pyroscope read theirs with `-config.expand-env=true`, which `compose.yaml` now passes them too. Each file holds both its local disk and S3, and the environment chooses: `TEMPO_BACKEND`, `LOKI_OBJECT_STORE` and `PYROSCOPE_BACKEND`;
  - Grafana expands `$VAR` in its provisioning, with no defaults, so the data sources' addresses are settings on `compose.yaml`'s Grafana, and defaults in its image;
  - LiteLLM's file already reads everything that differs from the environment.
- **No tool needed a file for AWS alone.**
- **`deploy/build-images` builds and checks them,** for the machine's architecture:
  - the Collector's, Tempo's and Loki's configuration, by the tool's own check, on one machine's settings and on the AWS recipe's;
  - that each image starts and answers its health check, on a Docker network of its own, which publishes no port and has no route out; LiteLLM's beside a Valkey, which it needs to start;
  - that Grafana has its four data sources and the three folders of dashboards.
- **The checks' helpers, curl and Valkey, are `compose.yaml`'s pins too.**
- **CI builds them natively on both architectures,** on `ubuntu-24.04` and `ubuntu-24.04-arm`, in a "Thin images" job, when they or the files they carry change, and nightly. It publishes nothing.

## Options considered

| Option | For | Against |
|---|---|---|
| **Native runners per architecture (chosen)** | Each image built and run where it will run; no emulation | Two runners per change |
| One runner, the other architecture under QEMU | One job | Slow, and a check under emulation shows less |
| **Dockerfiles beside each configuration (chosen)** | A service's files in one place | Eight directories with a Dockerfile |
| A `deploy/images/` directory | The images together | Each image's files far from its Dockerfile |
| **One file per service, the backend from the environment (chosen)** | One file for Compose and AWS, as the RFC asks | Each file carries both backends |
| A file for AWS alone, in the image | Each file simpler | Two files to keep in step |

## Consequences

- Easier: an image's configuration is the file Compose mounts, checked on both architectures, and on AWS's settings.
- Harder: the telemetry stores' files carry S3's settings, unused on one machine.
- Next: `stackr-db-init` and `stackr-auth-keys`; the release step that publishes the images, multi-arch, to GHCR; and tier 2, which runs them against Floci.
