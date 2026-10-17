# ADR-0036: Tier 2, against Floci

**Status:** Accepted, amended by [ADR-0037](0037-the-state-hosts-clickhouse-backups.md), and 2026-10-17 (see the [Amendment](#amendment-2026-10-17-the-manual-apply-comes-after-v01))
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

Builds [RFC-0004](../rfcs/0004-hosting-recipes.md)'s tier 2: `envs/floci` applied against Floci, with the thin images of [ADR-0035](0035-the-thin-images.md) and an application generated from the template, then smoked and destroyed. It amends the RFC's plan for tier 2 where Floci 2.2.0 couldn't follow it, and records each gap and what would lift it.

## Context

Tier 1 ([ADR-0029](0029-the-aws-modules-and-tier-1.md)) plans the recipe against a mocked AWS. It can't show that the stack runs: that tasks start, find each other and their data, and answer through the load balancer. RFC-0004 gives that to Floci, an AWS emulator that runs ECS tasks, RDS and ElastiCache as containers, and never to AWS itself. The [Floci spike](0025-what-the-floci-spike-found.md) settled which resources round-trip. Applying the whole stack found the rest.

## Decision

- **`deploy/aws/tier2` runs it, from one script.** It works the same on a laptop and in CI:
  1. It starts Floci and a registry for the images Floci pulls.
  2. It builds the eight thin images for arm64 and pushes them there.
  3. It generates an application from the template, with grantr and both libraries, locked at the pushed commit, and builds and pushes it too.
  4. It plans `envs/floci`, runs checkov over the plan, and applies it.
  5. It waits for every ECS service to run, smokes the stack, and destroys it.
- **Floci 2.2.0, pinned by digest.** It runs in Docker mode on a Docker network of the run's own, with these settings:
  - `FLOCI_HOSTNAME=floci`, so the addresses RDS and ElastiCache report are reachable from the tasks;
  - `FLOCI_DOCKER_RESOURCE_NAMESPACE` and `FLOCI_DOCKER_EXTRA_LABELS`, the run's id, which names and labels what Floci makes;
  - `FLOCI_SERVICES_ECS_TASK_ROLE_CREDENTIALS_ENABLED`, so tasks get their roles' credentials;
  - `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE`, `compose.yaml`'s PostgreSQL 17.
- **Floci's security-group enforcement stays off,** as [ADR-0025](0025-what-the-floci-spike-found.md) decided: with it on, tasks lose their roles' credentials, and Floci's load balancer, whose traffic comes from Floci's own container, reaches no target. Applying the whole stack found one more thing, which enforcement alone would fix: without it, a task's containers share no localhost (below). The groups' rules are still checked, by tier 1's tests and by checkov, and on AWS at the manual apply.
- **Everything is published on 127.0.0.1 alone:** Floci's API at `localhost:14566` and the registry at `localhost:15000` (`TIER2_FLOCI_PORT` and `TIER2_REGISTRY_PORT`), never `::1` or a wildcard. After the apply, the script fails if any container on the run's network is published anywhere else. The provider and the AWS CLI reach Floci at `localhost`, since S3 Control puts the account in the host's name, and a subdomain of `localhost` is the loopback too.
- **Nothing reaches AWS.**
  - The script reads none of the caller's AWS configuration: no config or credentials file, profile, session token or per-service endpoint.
  - Before it starts, it checks that `localhost`, and the account's subdomain of it that S3 Control asks for, resolve to the loopback alone.
  - It waits for Floci's own health on the loopback, then stops unless Floci answers as account `000000000000`, which AWS never is.
  - `envs/floci`'s provider names `var.endpoint` for each service the stack uses, which wins over any per-service endpoint in the environment. Its validation keeps that on the loopback, its static keys win over any profile, and its account is the one allowed.
  - The one-off tasks' AWS CLI, which OpenTofu runs, gets the same endpoint for each service it calls and no configuration file, so even a hand-run apply of `envs/floci` reaches only Floci.
- **On an arm64 Docker,** since the task definitions ask for ARM64, as Fargate runs them, and Floci runs every task on the host's own architecture. CI runs it on `ubuntu-24.04-arm`, and the script refuses another architecture.
- **checkov runs over the whole plan,** which the modules' own scans can't see, with `envs/floci/plan.checkov.yaml`'s skips. Each skip has its reason there, and nothing is skipped inline.
- **It waits for every ECS service the plan makes,** each running as many tasks as it desires, and stops with the tasks' logs if one doesn't.
- **The smoke runs from a container beside the stack,** which asks Floci's DNS server, as the tasks do, so it finds the services by their `stackr.internal` names. A key reaches curl on its standard input, never its command line. It checks:
  - the application, through the load balancer, by its Host header, and a request to it without a token, refused;
  - that the edge routes nothing to GoTrue's admin API: a 404, which is also what the listener answers for anything it doesn't route, so it shows no rule sends it on;
  - Langfuse's and Grafana's health;
  - a trace sent to the Collector, and found in Tempo;
  - LiteLLM, once its readiness endpoint answers (ECS counts its task running before it listens), answering with its mock's own words, for a key whose team allows mocks, as stackr's smoke's does;
  - through RDS's relay, as the application's role and as its owner, with the passwords from Secrets Manager: each one's `search_path`, the application's schema.
- **It removes only what it made, and never by a name pattern.** Each run has an id, which names its network, its two containers and its image tags. When it ends, however it ends, it destroys the stack, then removes:
  - its own two containers and its network, by the ids Docker gave them, with their volumes;
  - what Floci made, by the run's label, which Floci puts on every container and volume it creates, with their volumes;
  - the anonymous volumes Docker saw this run's containers mount, from its own events, recorded from before Floci starts: Floci removes a task's container without them when the destroy stops it;
  - Floci's networks, by the owner label Floci gives them, the run's namespace;
  - the image tags it pushed.
- **It shows that nothing is left.** It says what each step removes, and why. Then it checks again for anything with the run's labels, or an id it recorded, and fails if one is left. Nothing it creates outlives the run, except the images it pulls.
  - An interrupt can't cut the cleanup short. If the run is killed outright, `deploy/aws/tier2 --clean RUN` does the same from the record it keeps under the run's id.
  - A run's id may be chosen (`TIER2_RUN`), and the script refuses one that anything already carries.
- **CI runs it when its inputs change, and nightly.**
  - The `stackr:aws-tier2` task's inputs are the recipe, the images' files, the template, `copier.yml`, `uv.lock` and `.prototools`: what the application and the images are built from.
  - In CI, a small "AWS (tier 2) affected" job asks moon whether a pull request changes them, against the pull request's base, and logs what it compares. Only then does "AWS (tier 2)" start an arm64 runner. A library's change alone doesn't start Floci.
  - In the nightly workflow, it runs on its schedule and when run by hand, but not on each push to `main`. A push no longer cancels the night's run, whose concurrency group is its own.
  - Each run gets 60 minutes.
- **Each database role finds its schema by itself.** Floci's RDS drops what a client asks for when it connects (below), and so does any proxy that doesn't pass startup parameters on. So the roles carry their `search_path` in the application's database:
  - the template's `db-roles` sets the application's role's, which stackr's smoke checks as that role, right after `db-roles`;
  - db-init sets the owner's, from `APP_DB_SCHEMA`, which the stack takes from the application's `DATABASE_SCHEMA` (a plain lowercase identifier, as the template's settings take it), or the template's default, its package's name. db-init refuses an empty one, and resets the owner's when none is given. `deploy/build-images` checks it as the owner, right after db-init;
  - `db-roles` refuses a `DATABASE_URL` and `DATABASE_ADMIN_URL` on different databases, since it sets the role's `search_path` in the one it's connected to;
  - each check connects with psql, which asks for no `search_path`, so it sees the role's own, before anything is migrated. Tier 2 checks both again through Floci's relay.

## Floci 2.2.0's gaps

| Gap | What tier 2 does | What would lift it |
|---|---|---|
| A task's containers share no localhost unless security-group enforcement is on, which ADR-0025 keeps off | GoTrue through its proxy isn't smoked: Caddy can't reach GoTrue at `127.0.0.1:9998`. The script says it skips it, naming this ADR | Floci sharing a task's network namespace without enforcement, or enforcement that lets its load balancer and the tasks' credentials through. Then the check returns, as `answers "GoTrue, through its proxy" 200` |
| RDS's endpoint drops a client's startup parameters, such as asyncpg's `search_path` | The roles carry their `search_path` themselves (above), which holds on RDS too, and behind any such proxy | Nothing to lift: the roles' own setting stays |
| RDS's endpoint closes a TLS connection without TLS's close, so a client that asked for `ssl=prefer` logs `SSLEOFError` as it closes | Nothing fails: the error comes as the connection closes, after its work | Floci closing TLS properly |
| Cloud Map keeps a stopped task's instance, which AWS deregisters, and won't delete a service that has one | The script deregisters every instance before the destroy, and once more if a task that was still starting registered another | Floci deregistering a stopped task |
| ECS refused a key set given as a JSON key of a secret ("secret value is not a string") | The key set and the service role's key are each a whole secret ([ADR-0035](0035-the-thin-images.md)) | Nothing to lift: whole secrets ask nothing of ECS |
| Secrets Manager answers a secret without a value with no `SecretString`, where AWS refuses with `ResourceNotFoundException` | auth-keys takes both as no value | Nothing to lift |
| Floci pulls every task's image, even one Docker already has | The images go through a registry on the loopback | Nothing to lift: the registry costs a container |

**Not smoked yet,** each with what it waits on:

| Not smoked | Waits on |
|---|---|
| A user signing in through GoTrue, and an agent's turn and its trace | GoTrue through its proxy, above; or a sign-in at GoTrue's private address, whose tokens carry the same issuer, which can come first |
| psql through RDS's relay finding the role that owns nothing, and the row-level security policies | Nothing: its `search_path` is checked there already, and these are more queries of the same kind |
| Tempo's, Loki's and Langfuse's writes to S3 | Nothing in Floci: a check that waits for Tempo to flush a block, then lists its prefix in Floci's S3 |
| Loki answering a query | Nothing in Floci: a log line pushed, then asked for |
| The tasks' logs arriving in CloudWatch Logs | Nothing in Floci: a service's log stream read with `aws logs`, as `run-task` reads a one-off's |
| The state host's EC2 pieces: its user data, systemd timers, IMDS credentials, instance role and alert rules | Floci running the state host (ADR-0025). [ADR-0037](0037-the-state-hosts-clickhouse-backups.md) has tier 2 run its ClickHouse backups and drill against Floci's S3 in a ClickHouse of its own; the rest is tier 1's tests and the manual apply on AWS |

The single host's smoke covers the first two on Compose, and the manual apply on real AWS covers all of them on AWS.

## Options considered

| Option | For | Against |
|---|---|---|
| **Floci, enforcement off, as ADR-0025 decided (chosen)** | Every service runs, and the smoke fails only for the stack's reasons | The groups' rules aren't exercised on traffic, and GoTrue through its proxy isn't smoked |
| Floci, enforcement on | The groups' rules filter real traffic, and a task's containers share a localhost | As ADR-0025 found, and a run here again: the application's and GoTrue's targets time out; and the smoke's container, which no group names, can't reach Grafana or LiteLLM |
| A tier-2 step that sets the roles' `search_path` after the apply | Nothing changes in the product | The application fails until it lands, and only Floci's run is fixed, not a deployment behind another such proxy |
| LocalStack | Widely used | ECS, RDS and ElastiCache that run containers need its paid tier, and an account |
| AWS itself, in CI | The real thing | Never: RFC-0004 keeps AWS out of CI, and the manual apply covers it |

## Consequences

- Easier: a change to the recipe or an image is applied, run and smoked before it merges, on the architecture Fargate runs, and nothing it creates outlives the run, except the images it pulls.
- Harder: a tier-2 run takes about ten minutes on an arm64 runner, and runs on a change to `uv.lock` too. Floci's gaps are this ADR's to keep: each new Floci release is a chance to lift one.
- Next: what isn't smoked yet, above; the template's `hosting: aws`, the rest of RFC-0004's phase 4; and the manual apply on real AWS that gates stackr's v0.1.

## Amendment (2026-10-17): the manual apply comes after v0.1

[lattice ADR-0023's amendment](../../adr/0023-publishing-to-pypi-from-the-release-workflow.md#amendment-2026-10-16) releases stackr's 0.1.0 without waiting for the manual apply on real AWS, and [RFC-0004's amendment](../rfcs/0004-hosting-recipes.md#amendment-2026-10-17-the-manual-apply-comes-after-v01) records it: the apply is a stated limit of v0.1, not its gate. What this ADR leaves to the apply (the cannot-test list) is still checked there, and only there, after the release. Where it says the apply comes before stackr's v0.1, or calls it a gate, this supersedes it.
