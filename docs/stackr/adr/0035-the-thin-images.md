# ADR-0035: The thin images

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

Builds the thin images of [RFC-0004](../rfcs/0004-hosting-recipes.md)'s phase 3, for the settings [ADR-0034](0034-the-stack-on-aws.md) gives them: the six that carry a service's configuration, then the two one-off tasks', `stackr-db-init` and `stackr-auth-keys`, in the pull request after. It amends ADR-0034's table of those settings, for the telemetry stores' S3. The release that publishes them follows.

## Context

Fargate can't mount a checkout, so each service on Fargate whose configuration stackr owns runs a thin image: the upstream image `compose.yaml` pins, with stackr's files in it. RFC-0004 asks for one file per service, which reads from the environment whatever differs on AWS. ADR-0034 named those settings: each service's peers by their names in `stackr.internal`, and the telemetry stores' storage in S3.

Building the images settled the rest: where they're built from, how each tool takes its settings, and how CI shows that each one works on two architectures, since Fargate runs arm64 and tier 2's Floci runs the runners' amd64.

## Decision

- **Six images carry a service's configuration:** `stackr-otel-collector`, `stackr-tempo`, `stackr-loki`, `stackr-pyroscope`, `stackr-grafana` and `stackr-litellm`. Each is the image `compose.yaml` pins, with stackr's configuration copied in, and its command set to read it.
- **`stackr-db-init` is the PostgreSQL client `compose.yaml` pins, with `deploy/postgres/init.sql`,** run as the image's `postgres` user. The file gains what the AWS recipe needs, each part only when its settings are given, so one machine's db-init is unchanged:
  - Grafana's role and database, with `GRAFANA_DB_PASSWORD`, which only Grafana may connect to;
  - the application's database and its owner, with `APP_DB_NAME` and `APP_DB_PASSWORD`, on PostgreSQL 16 or later, which it refuses to go without. With grantr, `APP_DB_CREATES_ROLES` lets the owner create roles, for `db-roles`; on 16 and later, it administers only those it creates. Without grantr, the owner may not. The stack refuses an application named as one of its own roles or databases, or RDS's (`rdsadmin`, `rds_*`).
- **db-init keeps the statements that carry passwords out of the server's log where it may.** It sets `log_min_error_statement` and `log_min_duration_statement` for its own session, which a superuser, or RDS's `rds_superuser`, may. Where the server refuses, it goes on with the server's settings, and the AWS recipe's parameter group logs statements slower than a second: a password statement that failed, or took that long, would be in RDS's log, which only the account's operators read.
- **`stackr-auth-keys` runs `scripts/auth-keys`,** a command around `_auth_keys.py`, as RFC-0004 first named it, through boto3. It writes the key set to `AUTH_JWT_KEYS_ARN` only when that secret has no value. It writes the service role's key to `AUTH_SERVICE_ROLE_KEY_ARN` when that has none, or no longer verifies with the key set. Each write's request token is derived from what it's for, so of two runs at once, Secrets Manager takes the first's write, and the second reads it back. ADR-0034's one JSON secret becomes these two, each read whole: Floci's ECS refused the key set as a JSON key of it ("secret value is not a string"), and a whole secret asks nothing of ECS's JSON keys. Its dependencies are stackr's `auth-keys` group, as lattice's `uv.lock` pins them, which uv, from its own pinned image, installs into a virtual environment on the image's Python. The image runs as `nobody`, with no pip.
- **Each Dockerfile is beside its configuration,** as `deploy/<service>/Dockerfile`, labelled with lattice's repository, built from lattice's root, since Grafana's carries artifactr's and reflexr's dashboards. Each has its own `Dockerfile.dockerignore`, which lets in its files alone, as lattice's other images do.
- **Each base is its service's image, as `compose.yaml` pins it.** `scripts/check-config aws` fails when `deploy/<service>/Dockerfile`'s `FROM` isn't `<service>`'s image in `compose.yaml`, so Renovate's moves of the two stay together. LiteLLM's is now its non-root image, in both. auth-keys, which `compose.yaml` doesn't run, has its own pins, Python's and uv's.
- **Their files are read-only:** each `COPY` gives them `a=rX`, which keeps the execute bit only where a file had one, so auth-keys' virtual environment runs; and `--link` where the destination's directories are the image's own to make.
- **One file per service, as RFC-0004 asks.** It reads the AWS recipe's settings from the environment, with one machine's values by default, so Compose mounts the same file and changes nothing else:
  - the Collector reads `${env:TEMPO_ADDRESS:-tempo}` and its other peers so;
  - Tempo, Loki and Pyroscope read theirs with `-config.expand-env=true`, which `compose.yaml` now passes them too. Each file holds both its local disk and S3, and the environment chooses: `TEMPO_BACKEND`, `LOKI_OBJECT_STORE` and `PYROSCOPE_BACKEND`;
  - Grafana expands `$VAR` in its provisioning, with no defaults, so the data sources' addresses are settings on `compose.yaml`'s Grafana, and defaults in its image;
  - LiteLLM's file already reads everything that differs from the environment.
- **No tool needed a file for AWS alone.**
- **`deploy/build-images` builds and checks them,** for the machine's architecture:
  - the Collector's, Tempo's, Loki's and Pyroscope's configuration, by the tool's own check, on one machine's settings and on the AWS recipe's;
  - that each image starts and answers its health check, on a Docker network of its own, which publishes no port and has no route out; LiteLLM's beside a Valkey, which it needs to start;
  - that Grafana's four data sources are at their addresses, Compose's and then the AWS recipe's, and that it has the three folders of dashboards;
  - that db-init, as a `postgres` that may create roles and databases and is no superuser, as RDS's master, creates one machine's roles and databases and none of the AWS recipe's; then the AWS recipe's, twice; and that the application's owner may create and drop a role with grantr, and may not without;
  - that auth-keys refuses to start without its secrets, and says which, and that the script does what it should against a stubbed Secrets Manager: with nothing written yet, with both written, with a service role's key that no longer verifies, losing a race to write the key set, and when it is refused.
- **The checks' helpers, curl, Valkey and PostgreSQL, are `compose.yaml`'s pins too.**
- **CI builds them natively on both architectures,** on `ubuntu-24.04` and `ubuntu-24.04-arm`, in a "Thin images" job, whenever stackr, or a project it depends on, changes (`scripts/affected.py`), and nightly. It publishes nothing.

## Options considered

| Option | For | Against |
|---|---|---|
| **Native runners per architecture (chosen)** | Each image built and run where it will run; no emulation | Two runners per change |
| One runner, the other architecture under QEMU | One job | Slow, and a check under emulation shows less |
| **Dockerfiles beside each configuration (chosen)** | A service's files in one place | A Dockerfile in each image's directory |
| A `deploy/images/` directory | The images together | Each image's files far from its Dockerfile |
| **One file per service, the backend from the environment (chosen)** | One file for Compose and AWS, as the RFC asks | Each file carries both backends |
| A file for AWS alone, in the image | Each file simpler | Two files to keep in step |

## Consequences

- Easier: an image's configuration is the file Compose mounts, checked on both architectures, and on AWS's settings.
- Harder: the telemetry stores' files carry S3's settings, unused on one machine.
- Next: the release step that publishes the images, multi-arch, to GHCR; and tier 2, which runs them against Floci, auth-keys' write included.
