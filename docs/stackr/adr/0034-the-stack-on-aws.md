# ADR-0034: The stack on AWS

**Status:** Accepted, amended by [ADR-0035](0035-the-thin-images.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the third part of phase 3 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the `stack` module, which puts [ADR-0029](0029-the-aws-modules-and-tier-1.md)'s and [ADR-0032](0032-the-edge-the-services-and-the-state-host.md)'s modules together. `envs/prod` and `envs/floci`, its two roots, came in their own pull request; the thin images follow. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004's `stack` holds the cluster, the private namespace, every Fargate service, the state host and the one-off tasks. Putting them together found six things the RFC didn't settle:

- **Some secrets combine passwords.** Langfuse's encryption key must be 64 hexadecimal characters. LiteLLM's master key starts with `sk-`. Valkey's token goes to ElastiCache and into the connection strings that carry it. The Collector's credential for Langfuse is both of Langfuse's project keys, in Base64. The `secrets` module makes one password per secret, and writes it as it is or into templates.
- **The thin images' configuration names Compose's services,** such as `tempo:4317` and `langfuse-web:3000`. On Fargate they are `tempo.stackr.internal` and `langfuse-web.stackr.internal`.
- **Nothing runs a one-off task.** The RFC runs `db-init`, `auth-keys` and `db-roles` before the services that need them, by run-task, but OpenTofu has no resource that runs a task to its end.
- **Floci serves no TLS to RDS or ElastiCache,** and can't run the state host ([ADR-0025](0025-what-the-floci-spike-found.md)).
- **checkov follows `stack`'s module calls.** Scanning the directory reports each module's findings again, without the skips and reasons in that module's own configuration.
- **checkov over the plan's JSON** needs a plan that answers its data sources. A mocked test plans without producing one.

## Decision

### Its inputs

- **`images`, stackr's eight thin images, by digest, with no defaults.** Their defaults come with the images, which their own pull request builds. `envs/prod` pins them, and Renovate moves them.
- **The upstream images the stack runs as they are:** GoTrue, Langfuse's web and worker, and, on Fargate, ClickHouse, Prometheus and prom-label-proxy. Each is pinned in `locals.tf` as `compose.yaml` pins it, and `scripts/check-config aws` holds them to it.
- **`application`,** the application generated from the template: its name (`project_slug`), its image, its access (`grantr` or `none`), and its own settings and secrets. The stack gives it the rest:
  - the Collector, Langfuse and LiteLLM, at their private names;
  - GoTrue's issuer at `auth.<domain>`, and its key set and admin API at its private address;
  - Langfuse's project keys;
  - its database URLs, with `ssl=require`, as asyncpg takes them.
- **With `grantr`, the application gets two database URLs,** the role it works as and the tables' owner, with the service role's key and `db-roles` ([ADR-0022](0022-row-level-security-in-the-template.md)). With `none`, it gets one URL, the owner's.
- **`state_host`,** `ec2` on AWS, or `fargate` for Floci: it refuses `fargate` unless the deployment is destroyable and has Floci's `aws_endpoint_url`.
- **Floci's switches:**
  - `tls_to_data`, off on Floci, which serves no TLS to RDS or ElastiCache: `sslmode=prefer` in place of `require`, `redis://` in place of `rediss://`, and Grafana's `disable`;
  - `aws_endpoint_url`, Floci's address for the services that call S3 and Secrets Manager;
  - `destroyable`. One switch, not one per resource: on, a destroy takes RDS without a final snapshot, empties the buckets, deletes the secrets at once, skips the state host's volume's snapshot, and lets the ALB go. The stack's tests check its own secrets' recovery window both ways; the `data`, `edge` and `state-host` modules' tests check their guards.
- **`run_task_environment`,** what the AWS CLI that runs the one-off tasks needs beside OpenTofu's own environment: the provider's credentials, when the provider is given them otherwise. `envs/prod` passes its `profile` as `AWS_PROFILE`, and `envs/floci` Floci's keys and address.

### Secrets

- **The `secrets` module makes most of them,** and gains a `template` for a secret that isn't JSON, such as `sk-{password}`, and a `{password_sha256}` placeholder, 64 hexadecimal characters, for Langfuse's encryption key. It refuses a template without either placeholder, which would be written as it is.
- **The databases' secrets are a second instance of it,** since their URLs carry RDS's address. Each is JSON, with the role's `password`, which `db-init` reads, and its `url`, which its service reads. Their keys start with `database-`, so the two instances never collide.
- **Two are written in `stack`,** from ephemeral passwords of their own, with `secret_string_wo`:
  - **Valkey's,** with its token and the connection strings for Langfuse (database 0) and LiteLLM (database 1). ElastiCache is given the same ephemeral token, so nothing reads a secret back, which a mocked test couldn't do. The two are written in one apply. If one stops after ElastiCache is made but before the secret is written, the next apply's password differs from ElastiCache's: raising Valkey's version writes both again.
  - **Langfuse's project keys,** `public` and `secret`, with `otlp_auth`, the Collector's Basic credential, made of both.
- **`secret_versions` rotates a secret by its key, and only those that can.** It takes Langfuse's NextAuth secret, LiteLLM's master key, GoTrue's JWT secret, Valkey's, and the databases'. It refuses the others:
  - Langfuse's salt and encryption key, and LiteLLM's salt key, encrypt data;
  - Langfuse's project keys and admin password, and Grafana's admin password, are read on their first start only;
  - ClickHouse's passwords reach the state host only when its unit restarts, which nothing here does.
- **A rotation reaches its readers.** db-init runs again for a database's version. Each service's `after` carries the versions of the secrets it reads, so a rotated one deploys it again, with new tasks, and only the services that read it.
- **A secret is written when its version is raised, and only then.** Replacing what a secret's value names, such as RDS behind a database's URL, needs its version raised too.
- **The secrets OpenTofu writes are written before a service reads them:** the ARNs the services are given come from the secret versions. Those it doesn't write are another matter. GoTrue's key set and the service role's key are written by the auth-keys task, which GoTrue and the application wait for. The providers' API keys and GoTrue's SMTP password are written by an operator: LiteLLM and GoTrue fail to start until they are, and after writing one, an operator deploys its reader again (`aws ecs update-service --force-new-deployment`), since OpenTofu can't see its version.

### The thin images' environment

Each thin image reads what differs on AWS from its environment. It defaults to Compose's names on one machine, as RFC-0004 asks ("one file per service"). The stack sets:

| Image | Settings |
|---|---|
| `stackr-otel-collector` | `TEMPO_ADDRESS`, `PROMETHEUS_ADDRESS`, `LOKI_ADDRESS`, `LANGFUSE_ADDRESS`; `STACKR_ENVIRONMENT`, `STACKR_TRACES_EXPORTERS`; `LANGFUSE_OTLP_AUTH`, a secret |
| `stackr-tempo`, `stackr-loki`, `stackr-pyroscope` | `PROMETHEUS_ADDRESS`, for Tempo's metrics; their S3 backend, by each one's name for it (`TEMPO_BACKEND=s3`, `LOKI_OBJECT_STORE=aws`, `PYROSCOPE_BACKEND=s3`); `S3_BUCKET`, `S3_REGION`, and `S3_PREFIX`, its own under the telemetry bucket (`tempo`, `loki`, `pyroscope`, with no trailing slash: Pyroscope joins a prefix to its keys with one, so a slash of its own would make an empty segment); and `S3_ENDPOINT`, `S3_INSECURE` and `S3_PATH_STYLE` (`S3_BUCKET_LOOKUP_TYPE`, as Pyroscope names it), S3's host and port, plain HTTP, and buckets as paths, which only Floci's needs. They reach S3 at `S3_ENDPOINT` alone, so they get no `AWS_ENDPOINT_URL`. Their task roles may list their prefix and below it, and reach the objects under `<prefix>/` |
| `stackr-grafana` | `TEMPO_ADDRESS`, `LOKI_ADDRESS`, `PYROSCOPE_ADDRESS`, `PROMETHEUS_ADDRESS`; `GF_DATABASE_*`, on RDS, with `GF_DATABASE_SSL_MODE`; its admin's and its database's passwords, secrets |
| `stackr-litellm` | `compose.yaml`'s settings, with `DATABASE_URL`, `REDIS_URL` and its keys as secrets, and one `<PROVIDER>_API_KEY` secret for each of `gateway_providers`, which an operator writes |
| `stackr-db-init` | `PG*`, as RDS's master, `postgres`, with `PGSSLMODE` and `PGPASSWORD` from RDS's own secret; the roles' passwords, as on one machine, with `GRAFANA_DB_PASSWORD`; and the application's database, `APP_DB_NAME` and `APP_DB_PASSWORD`, its owner's, which may create roles for `db-roles` |
| `stackr-auth-keys` | `AUTH_JWT_KEYS_ARN` and `AUTH_SERVICE_ROLE_KEY_ARN`, the two secrets it writes, each whole, as GoTrue and the application read them; its task role may read and write those two alone |

The images' pull request implements these settings, with Compose's defaults.

### The one-off tasks

- **Each is run by `run-task` from the machine that applies,** through a `terraform_data` with a `local-exec` that calls `modules/stack/run-task`. The script:
  1. starts the task with the AWS CLI, in the private subnets, and fails when ECS can't place it;
  2. waits for it to stop, for up to 30 minutes;
  3. fails with its exit code and its stopped reason.
- **It runs when its task definition changes.** db-init also runs when a database's version is raised, and db-roles when the application's are, and after each db-init. auth-keys writes the key set only when its secret is empty, and the service role's key only when it is missing or signed with a key the set no longer has, so running it again changes nothing. Planning runs nothing, so tier 1 needs no AWS.
- **db-roles has only what it needs:** the application's two database URLs, and its schema setting, if it gives one.
- **The services wait for what they need.** `ecs-service` gains `after`, what a service waits for, which becomes its `triggers`, with `force_new_deployment`: a trigger alone would update the service in place and keep its tasks. Only its ECS service waits, not its task definition. A module's `depends_on` would defer its data sources to the apply, and with them every policy the tests read.
  - GoTrue waits for db-init and auth-keys; the application for db-init and, with `grantr`, db-roles and auth-keys; Langfuse's, LiteLLM's and Grafana's for db-init.
  - Langfuse and the Collector wait for the state host's instance, or its three services on Fargate. Nothing at plan time waits for what the instance's user data starts: ClickHouse may come up after Langfuse, whose tasks fail and are replaced until it is. Tier 2 shows whether the circuit breaker allows for it. A new instance, such as an AMI's bump, deploys them again too.
  - **Langfuse's worker waits for the web server's migrations,** as on one machine ([#155](https://github.com/alexnodeland/lattice/issues/155)): it writes Langfuse's default models as it starts, which can deadlock a migration. ECS orders no service after another, so the worker's task holds a `wait` container, which `ecs-service` gains, that must exit 0 before the worker starts. It polls the web server's health until it answers as the worker's own version, which it does only once migrated: on a first deployment, and on an upgrade, while the old web tasks still answer as the old version. Each try gives up after 5 seconds, and the wait after 30 minutes, which stops the task; ECS's own `startTimeout` is left alone, since Fargate caps it at 120 seconds. While the web server is down, no new worker task starts. A check, and a tier-1 test, hold the two images to one version. Tier 2 confirms that a failed wait stops the task, and how the deployment circuit breaker takes it.
- **A task definition is named only once its roles' policies are written,** and `run-task` runs a task again, a few times, when it can't start for want of its secrets or image (`ResourceInitializationError`), as when IAM hasn't yet propagated a new role's policy.
- **The edge's target groups wait for their listener rules,** since ECS refuses a service whose target group no listener forwards to.
- **Applying needs AWS CLI v2** where OpenTofu runs. On Floci, `AWS_ENDPOINT_URL` points it there.
- **Each run waits for the network,** whose route out it needs to pull its image and read its secrets. db-init and db-roles also wait for the security groups' rules: their groups reach nothing else, so without the rule to PostgreSQL, psql times out.

### A security group per service

Each service and one-off task has a group of its own, with a rule from each of its callers, on its port, and nothing else, as RFC-0004 asks. It replaces [ADR-0032](0032-the-edge-the-services-and-the-state-host.md)'s one group for every service.

- **One table in `stack`, `groups.tf`, says who calls whom.** Each line is a service's port and its callers, and the rules, one each way, are made from it. A module makes its own group, and `stack` gives it the rules: the data stores', the state host's and the ALB's. The modules don't know their callers; `stack` does, and one table is one list the tests check whole. A name the table doesn't know fails the plan.
- **Every task also has the tasks group,** `network`'s, which reaches out over HTTPS alone. Each task needs it: Fargate pulls its image and reads its secrets through it, its logs go to CloudWatch, Langfuse and the telemetry stores reach S3, and LiteLLM its providers. VPC endpoints could take AWS's own traffic off it later. auth-keys needs nothing else. GoTrue's group also reaches its SMTP server, when it has one.
- **On EC2, the state host is one group** for ClickHouse, Prometheus and prom-label-proxy, and for Prometheus's scrapes and the operators' port forwarding to Grafana, Langfuse and LiteLLM. One rule covers each pair of groups and port, so a scrape of Grafana and a forward to it are one rule. On Fargate, each of the three has its own group, and Prometheus scrapes only itself, so it calls no service.
- **portalr reads Prometheus through prom-label-proxy, Tempo and Loki, from inside the application,** so the application calls all three, and gets their addresses as `PORTALR_PROXY_URL`, `PORTALR_TEMPO_URL` and `PORTALR_LOKI_URL` (portalr's ADR-0012). The template doesn't push profiles, so only Grafana and the state host's Prometheus call Pyroscope.
- **The test is the proof:** Floci doesn't enforce security groups (ADR-0025). `tests/stack.tofutest.hcl` lists every rule, and fails on one more or one fewer, and checks that each rule is between the groups its names say.

### ClickHouse, Prometheus and prom-label-proxy on Fargate, for Floci

- **ClickHouse has no `users.xml`, on Floci only:** without the state host, there is no checkout to mount it from, and no thin image carries it. Its image's own setup makes one user, `langfuse`, from `CLICKHOUSE_USER` and `CLICKHOUSE_PASSWORD`, with the image's full grant, and no admin, so the admin's password isn't made. Langfuse's settings are the same in both places.
- **Prometheus** takes its metrics by OTLP and remote write, with `compose.yaml`'s flags, and scrapes only itself.
- **prom-label-proxy** listens on 9091, the state host's port.
- **Each has a group of its own,** with its callers' rules, on Fargate only.

### checkov

- **Each module is scanned on its own files** (`--file`), with its own skips: the stack's are its two hand-written secrets', with the `secrets` module's reasons.
- **checkov over the plan's JSON waits for tier 2** (phase 4), where `envs/floci` plans against Floci, which answers the data sources.

### The roots

`envs/prod` and `envs/floci` came in the pull request after `stack`'s.

- **`envs/prod`** keeps its state in S3 with `use_lockfile`, in one bucket per account, which its README makes by hand (versioned, encrypted, private, TLS only, its old versions expired), and one key per deployment, `<name>/terraform.tfstate`, from a `<deployment>.s3.tfbackend` given at `tofu init`. A deployment's settings are in its own `.tfvars`, from `prod.tfvars.example`; the repository ignores both. Its provider applies only to `account_id`, with the credentials of `profile`, a role's through a profile with `role_arn`, or the shell's. Until stackr's release publishes the thin images, their digests are settings too. Tier 1 plans `prod.tfvars.example` against a mocked AWS.
- **`envs/prod` exposes what an operator chooses, and fixes the rest** at the stack's defaults, every guard included; its README lists them, and how to retire a deployment past them.
- **`envs/floci` fails closed.** Its provider reaches Floci through `AWS_ENDPOINT_URL`, with Floci's keys, which AWS refuses, and applies only to Floci's account, `000000000000`, which no AWS account is; the one-off tasks' AWS CLI gets the same keys and Floci's address, which must be on the loopback or Floci's own network. It has local state, and runs the state host's services on Fargate, without TLS to the data stores, destroyable, with Valkey on a port in Floci's range, and with the domain's zone made in Floci.
- **Each root has its own lock file,** the tests' own, for `linux_amd64`, `darwin_arm64` and `darwin_amd64`. Tier 1 validates each root against it, and fails when it differs from the tests'.

### Where this departs from RFC-0004

- **`envs/prod` and `envs/floci` were their own pull request,** after `stack`'s, to keep each under review's size.
- **The thin images' digests are a deployment's settings** until stackr's release publishes them.
- **The one-off tasks run from where OpenTofu runs,** which needs the AWS CLI there. The RFC said only "by run-task".
- **The application's settings come from the stack,** and not from a root of the template's. The template's `hosting: aws` root will call `stack` with its image and its own settings.
- **Langfuse's bucket has no CORS configuration,** which browsers' media uploads to it need. Traces and events don't; the manual gate checks it.
- **`envs/floci`'s tests wait for tier 2,** where they apply against Floci; the RFC puts them beside the root.
- **checkov over the plan's JSON waits for tier 2,** which RFC-0004 puts in tier 1: a mocked test makes no plan to scan.

## Options considered

| Option | For | Against |
|---|---|---|
| **A run per one-off, from the machine that applies (chosen)** | Runs once, before the services that need it, and fails the apply when it fails | Needs the AWS CLI where OpenTofu runs |
| Each one-off as a container in its services' tasks | Nothing beyond ECS | Runs once per task, in parallel: two `auth-keys` would race to write the first key set |
| An operator runs them by hand | Nothing in OpenTofu | A first apply's services fail until someone does |
| **`after`, as the ECS service's `triggers` (chosen)** | Only the service waits; a new run deploys it again | One more input to `ecs-service` |
| A module's `depends_on` | Plain OpenTofu | Defers every data source in the module to the apply, so plans and tests can't read the policies |
| **Valkey's token from an ephemeral password in `stack` (chosen)** | Nothing reads a secret back; tests mock everything | Valkey's secret is written outside the `secrets` module |
| An ephemeral read of the token's secret | One place that makes secrets | OpenTofu can't mock an ephemeral resource, so the stack couldn't be tested |
| **Peers' addresses as settings (chosen)** | One configuration file per service, for Compose and AWS | Settings the images must read |
| A DNS search domain of `stackr.internal` | No settings | Rests on Fargate following the VPC's DHCP options, which nothing here has confirmed |
| **checkov on each module's own files (chosen)** | Each finding once, with its module's skips and reasons | A finding about how modules combine is left to review |
| checkov on the stack's directory | Sees the modules combined | Reports every module's findings again, without their skips |
| **Floci's ClickHouse with the image's one user (chosen)** | No image of stackr's for Floci alone | Floci's ClickHouse has no admin, and Langfuse's user has the full grant |
| A thin ClickHouse image with `users.xml` | The same users everywhere | One more image, for a service the state host runs from a checkout |
| **A group per service, from one table in `stack` (chosen)** | Every rule in one place, tested against one list | `stack` holds the rules of the groups other modules make |
| Each module takes its callers' groups | Each module's rules beside its group | The callers are the stack's to know, and the rules would be in seven places, each tested apart |
| **The application as portalr's readers' caller (chosen)** | portalr, which reads prom-label-proxy, Tempo and Loki, runs in the application | Rules for an application that doesn't mount portalr |
| No caller for them | No rule nothing uses | portalr couldn't reach them once mounted |
| **One `destroyable` switch (chosen)** | One setting a deployment can't half set | No deployment keeps some guards and drops others |
| A variable per guard | Each guard chosen alone | Five settings that must agree |

## Consequences

- Easier: the stack plans whole against a mocked AWS. Its tests check:
  - that no secret is a setting, and that each secret reaches the services that read it;
  - GoTrue behind its proxy, and its SMTP;
  - the edge's target groups, and each task role's bucket and prefix;
  - every security group rule, and the groups each joins;
  - what each service waits for, and what a rotation deploys again;
  - the application with and without `grantr`;
  - both places the state host's services run.
- Easier: one switch makes a deployment one a destroy takes whole.
- Harder: applying needs the AWS CLI, and the thin images must read the settings above.
- Next: the thin images, with the settings above; their digests pinned in `envs/prod`, with a Renovate manager for `envs/` (today's matches only `modules/`); VPC endpoints for AWS's own traffic; then tier 2, with `envs/floci`'s tests and checkov over the plan's JSON.
