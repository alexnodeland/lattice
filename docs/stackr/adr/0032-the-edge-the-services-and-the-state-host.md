# ADR-0032: The edge, the services, and the state host

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the second part of phase 3 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the `edge`, `ecs-service` and `state-host` modules, after [ADR-0029](0029-the-aws-modules-and-tier-1.md)'s tools and first three. `stack`, `envs/prod` and `envs/floci` follow, then the thin images. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004 serves the application at `app.<domain>` and GoTrue at `auth.<domain>` through an ALB; runs every stateless service on Fargate, each with its secrets from Secrets Manager; and keeps ClickHouse, Prometheus and prom-label-proxy on one EC2 state host, under Compose and systemd, with its data on an EBS volume that DLM snapshots, as [ADR-0025](0025-what-the-floci-spike-found.md) settled. It says the state host reuses the single host's Compose.

Building it found three things the RFC didn't say:

- Compose won't read a file without every variable it requires, for any of its services, so the state host can't run three services of `compose.yaml` without the whole stack's `.env`.
- The ALB appends the address it sees to the `X-Forwarded-For` a client sends. GoTrue's per-address rate limits read that header's first value ([ADR-0026](0026-the-single-host.md)), which behind the ALB is the client's to choose: a forged value is a fresh rate limit on every request. The ALB can keep, append to, or remove the header, but not replace it. On the single host, Caddy replaces it.
- The ALB can set some of the single host's response headers, but not `Referrer-Policy`.

## Decision

### The edge

- **An ALB with one ACM certificate for both names,** validated through the domain's Route 53 zone, which also names the ALB.
- **HTTP only redirects.** HTTPS offers TLS 1.3 and 1.2 (`ELBSecurityPolicy-TLS13-1-2-2021-06`), drops invalid headers, and answers 404 to any other host.
- **The single host's response headers, where the ALB can set them:** HSTS, `X-Content-Type-Options: nosniff`, and no `Server`. GoTrue's proxy sets `Referrer-Policy` for `auth.<domain>`; the application sets its own.
- **`app.<domain>` goes to the application's target group,** on 8000, checked at `/healthz`. **`auth.<domain>` goes to GoTrue's,** on 9999, checked at `/health`, after a rule that refuses `/admin` and `/admin/*` there with 404. Caddy refuses `/admin/*` on the single host; the ALB's rule also refuses `/admin` itself.
- **Its access logs go to `data`'s `access-logs` bucket,** under `alb/`, which ELB's log delivery may write to for this account's load balancers only.
- **The ALB refuses to be deleted** unless its variable says otherwise.

### GoTrue's proxy

- **GoTrue's task runs Caddy in front of it.** Caddy takes GoTrue's port, 9999, which the target group and the other services reach, and GoTrue listens on the task's loopback, at 9998. The edge holds Caddy's configuration (`auth-proxy.Caddyfile.tftpl`) and gives it, with Caddy's image, as its `auth_proxy` output. `ecs-service` runs it as a `proxy` beside its container, with the configuration in its environment, so it needs no image of its own.
- **Caddy trusts only the ALB's subnets,** the public subnets' ranges, as proxies. It reads `X-Forwarded-For` from the right, skipping the trusted addresses, takes the first it doesn't trust, which the ALB added, and passes GoTrue that one address. A caller inside the VPC, such as the application's admin commands, is its own address. It runs the single host's Caddy, by the same digest, which `scripts/check-config aws` holds it to.
- **Tier 1 runs it.** `tests/auth-proxy` starts Caddy with the rendered configuration on an internal Docker network, which publishes nothing. It checks what GoTrue is given for a forged header from the ALB's range, past a second trusted hop, and from outside the range.

### A service

- **`ecs-service` is one Fargate service on Graviton (ARM64):**
  - its container, and a proxy in front of it when it is given one;
  - its logs, in CloudWatch Logs for a short while, for when the Collector itself is down;
  - its name in the private namespace, `<name>.stackr.internal`;
  - its target group, when the edge reaches it;
  - a deployment circuit breaker that rolls back.
- **Settings are environment; secrets are references.** A secret is a Secrets Manager ARN, or `<arn>:<json key>::`, and a setting is never both, which the variables refuse. They also refuse a target group on a one-off task or a service without a port, and a proxy without a port.
- **The execution role may do three things,** each inline: write to its own log group; read exactly its secrets, by their ARNs; and pull from ECR, only from the repositories it is given. The images are public, on GHCR and Docker Hub, so by default it pulls from none. The task role holds only what a caller gives it, such as Langfuse's bucket.
- **Both roles trust only this account's ECS tasks** (`aws:SourceAccount`, `aws:SourceArn`), against the confused deputy.
- **A one-off task,** such as `db-init`, `auth-keys` or the application's `db-roles`, is its task definition alone, which the recipe runs by run-task: no service and no name.

### The state host

- **One EC2 instance, Ubuntu 24.04 on Graviton, from a pinned AMI:**
  - IMDSv2 only, one hop away: the AWS CLI reads the secrets on the host's network, and the services' containers, on Compose's network, can't reach it;
  - an encrypted root disk;
  - an instance profile that lets SSM's agent register as one of this account's instances and run sessions, and reads ClickHouse's two passwords. It reads none of SSM's parameters;
  - no SSH key.
- **A new AMI is a deliberate bump.** `ami_id` is a variable, since a new AMI replaces the instance, which stops ClickHouse and Prometheus for minutes. To bump it, read the ID that SSM's `/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id` names in the deployment's region, set it, and apply. RFC-0004's phase 5 puts this in the hosting guide.
- **Its data volume is its own:**
  - encrypted, mounted at `/data` by its id, and formatted only when it has no filesystem;
  - snapshotted daily by DLM, keeping 14;
  - snapshotted again before a destroy (`final_snapshot`, a variable);
  - detached only after the instance stops, when it is replaced.
- **Its address is fixed,** on a network interface that outlives the instance. `clickhouse`, `prometheus` and `prom-label-proxy` are named at it in the private namespace.
- **Its own security group,** with the services' group's rules to and from it in the same module:
  - in, ClickHouse's, Prometheus's and prom-label-proxy's ports, from the services;
  - out to the services' ports that Prometheus scrapes and operators forward to (`service_ports`), which the services' group takes from it in turn;
  - out over HTTPS, for lattice's checkout, its images and AWS's APIs, and over HTTP, for Ubuntu's arm64 packages, whose mirror is plain HTTP, with signed packages.
- **Its first boot:**
  1. writes Docker's log rotation, then installs Docker and Compose;
  2. formats the volume the first time and mounts it;
  3. checks out lattice at a commit, by its SHA, which can't move as a tag can;
  4. starts a systemd unit that runs `deploy/aws/state-host`'s Compose at every boot.
- **Each time the unit starts,** it reads ClickHouse's passwords, Langfuse's and its admin's, from Secrets Manager into `/run/stackr/.env`, on tmpfs and private, through the AWS CLI's pinned image. Nothing rests on disk, and a rotated secret reaches the host with `systemctl restart stackr-state`.
- **Its backups are DLM's snapshots,** as RFC-0004's H12 chose. They are crash-consistent: ClickHouse recovers from one as from a power cut. [ADR-0027](0027-the-single-hosts-backups.md)'s `BACKUP ... TO S3`, its `backup` user and its drill aren't carried over yet ([#149](https://github.com/alexnodeland/lattice/issues/149)). Until then, an operator restores a volume from a snapshot at each upgrade, as [RFC-0004's restore drill](../rfcs/0004-hosting-recipes.md#operations) says.

### Where this departs from RFC-0004

- **The state host's Compose is a file of its own, `deploy/aws/state-host/compose.yaml`, not an overlay on `compose.yaml`.** Compose needs every variable that a file requires, for every service in it. So an overlay would need the whole stack's `.env` on the state host, secrets included, to start three services. Its services are `compose.yaml`'s but for their ports and their data's paths on the host: the same images, users, commands, health checks, settings and mount points. Its Prometheus configuration is `deploy/prometheus/prometheus.yml` with the services named in `stackr.internal`. `scripts/check-config aws` fails when any of these drifts, and `make validate` runs it.
- **Its ports bind the instance's private address,** not every interface.
- **Its ClickHouse has [ADR-0031](0031-clickhouses-admin-apart-from-langfuse.md)'s users from its first version:** `deploy/clickhouse/users.xml`, the same file as on one machine. `admin` is for operators, and Langfuse's user reaches only its own database and the system tables it reads.
- **It checks out a commit, not a tag,** and its AMI is pinned, not looked up.
- **GoTrue's task has a second container,** Caddy, for the address its rate limits read.

### Design debt

- **The services share one security group.** Each service takes traffic from every other on every service port, not only from the services that call it, as RFC-0004 asks. A group per service, with rules from its callers, comes with `stack`, which knows who calls whom.
- **The state host reaches the internet** over HTTP and HTTPS, through the NAT gateway. VPC endpoints for Secrets Manager, SSM, `ssmmessages` and `ec2messages` would keep AWS's traffic off it. Removing its internet access would also need an ECR pull-through cache for its images, lattice's checkout from S3, and an HTTPS mirror for Ubuntu's packages, which would also close port 80.

## Options considered

| Option | For | Against |
|---|---|---|
| **Caddy beside GoTrue, trusting the ALB's subnets (chosen)** | The single host's rules and the same Caddy; GoTrue is given one address it can trust; nothing outside the task changes | A second container in GoTrue's task |
| CloudFront in front of the ALB, with `CloudFront-Viewer-Address` | A header the client can't set | Another service and certificate, and GoTrue reads only `X-Forwarded-For` |
| The ALB's `remove` mode for `X-Forwarded-For` | One setting | GoTrue then has no address, and applies no rate limit at all |
| **The state host's own Compose file (chosen)** | Needs only its own three settings | Its services are written twice, which a check keeps in step |
| An overlay on `compose.yaml` | One definition of each service | Needs the whole stack's `.env`, secrets included, on the state host |
| **Compose on a plain EC2 instance (chosen)** | The single host's recipe, and a volume that outlives replacing the instance | Outside the ECS cluster, so a boot and a unit of its own |
| An ECS container instance with a volume | One cluster for everything | ECS's EBS volumes belong to a task and go with it, as RFC-0004 found |
| **A pinned AMI (chosen)** | An apply never replaces the instance unasked | A bump by hand |
| SSM's current AMI, with `ignore_changes` | The latest at the first apply | The AMI in use hides in state, and replacing the instance needs `-replace` |

## Consequences

- Easier: the edge, each service and the state host are each one module, tested against a mocked AWS for their security properties, with checkov's skips per module. GoTrue's proxy runs in tier 1.
- Easier: rotating ClickHouse's passwords is a restart of the state host's unit.
- Harder: the state host's three services are written twice, which a check keeps in step; and its AMI moves by hand.
- Next: `stack`, which puts them together, and `envs/prod` and `envs/floci`, where the state host's services run on Fargate (ADR-0025); a security group per service; the state host's ClickHouse backups ([#149](https://github.com/alexnodeland/lattice/issues/149)).
