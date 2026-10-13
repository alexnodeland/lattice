# ADR-0032: The edge, the services, and the state host

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the second part of phase 3 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the `edge`, `ecs-service` and `state-host` modules, after [ADR-0029](0029-the-aws-modules-and-tier-1.md)'s tools and first three. `stack`, `envs/prod` and `envs/floci` follow, then the thin images. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004 serves the application at `app.<domain>` and GoTrue at `auth.<domain>` through an ALB; runs every stateless service on Fargate, each with its secrets from Secrets Manager; and keeps ClickHouse, Prometheus and prom-label-proxy on one EC2 state host, under Compose and systemd, with its data on an EBS volume that DLM snapshots, as [ADR-0025](0025-what-the-floci-spike-found.md) settled. It says the state host reuses the single host's Compose. Building it found that Compose won't read a file without every variable it requires, for any of its services, so the state host can't run three services of `compose.yaml` without the whole stack's `.env`.

## Decision

### The edge

- **An ALB with one ACM certificate for both names,** validated through the domain's Route 53 zone, which also names the ALB.
- **HTTP only redirects.** HTTPS offers TLS 1.3 and 1.2 (`ELBSecurityPolicy-TLS13-1-2-2021-06`), drops invalid headers, and answers 404 to any other host.
- **`app.<domain>` goes to the application's target group,** on 8000, checked at `/healthz`. **`auth.<domain>` goes to GoTrue's,** on 9999, checked at `/health`, after a rule that refuses `/admin` and `/admin/*` there with 404, as Caddy does on the single host.
- **The ALB refuses to be deleted** unless its variable says otherwise.

### A service

- **`ecs-service` is one Fargate service on Graviton (ARM64):**
  - its one container;
  - its logs, in CloudWatch Logs for a short while, for when the Collector itself is down;
  - its name in the private namespace, `<name>.stackr.internal`;
  - its target group, when the edge reaches it;
  - a deployment circuit breaker that rolls back.
- **Settings are environment; secrets are references.** A secret is a Secrets Manager ARN, or `<arn>:<json key>::`, and a setting is never both, which the variables refuse. The execution role may read exactly those secrets, by their ARNs. The task role holds only what a caller gives it, such as Langfuse's bucket.
- **Both roles trust only this account's ECS tasks** (`aws:SourceAccount`, `aws:SourceArn`), against the confused deputy.
- **A one-off task,** such as `db-init`, `auth-keys` or the application's `db-roles`, is its task definition alone, which the recipe runs by run-task: no service and no name.

### The state host

- **One EC2 instance, Ubuntu 24.04 on Graviton,** from the AMI Canonical names in SSM:
  - IMDSv2 only, with a hop for the AWS CLI's container;
  - an encrypted root disk;
  - an instance profile that allows SSM's Session Manager and reading ClickHouse's two passwords, nothing more;
  - no SSH key.
- **Its data volume is its own:** encrypted, mounted at `/data` by its id, and snapshotted daily by DLM, keeping 14.
- **Its address is fixed,** on a network interface that outlives the instance. `clickhouse`, `prometheus` and `prom-label-proxy` are named at it in the private namespace.
- **Its own security group:** in, ClickHouse's, Prometheus's and prom-label-proxy's ports, from the services only; out, HTTP and HTTPS alone, for its packages, lattice's checkout, its images and Secrets Manager. The services' egress to it is in the same module.
- **Its first boot:**
  1. installs Docker and Compose;
  2. formats the volume the first time and mounts it;
  3. checks out lattice at a tag;
  4. reads ClickHouse's passwords, Langfuse's and its admin's, from Secrets Manager into a private `.env`, through the AWS CLI's pinned image;
  5. starts a systemd unit that runs `deploy/aws/state-host`'s Compose at every boot.

### Where this departs from RFC-0004

- **The state host's Compose is a file of its own, `deploy/aws/state-host/compose.yaml`, not an overlay on `compose.yaml`.** Compose needs every variable that a file requires, for every service in it. So an overlay would need the whole stack's `.env` on the state host, secrets included, to start three services. Its images are `compose.yaml`'s, and its Prometheus configuration is `deploy/prometheus/prometheus.yml` with the services named in `stackr.internal`. `scripts/check-config state-host` fails when either drifts, and `make validate` runs it.
- **Its ports bind the instance's private address,** not every interface.
- **Its ClickHouse has [ADR-0031](0031-clickhouses-admin-apart-from-langfuse.md)'s users from its first version:** `deploy/clickhouse/users.xml`, the same file as on one machine. `admin` is for operators, and Langfuse's user reaches only its own database and the system tables it reads.

## Consequences

- Easier: the edge, each service and the state host are each one module, tested against a mocked AWS for their security properties, with checkov's skips per module.
- Harder: the state host's three services are written twice, which a check keeps in step.
- Next: `stack`, which puts them together, and `envs/prod` and `envs/floci`, where the state host's services run on Fargate (ADR-0025).
