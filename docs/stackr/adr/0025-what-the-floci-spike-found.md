# ADR-0025: What the Floci spike found

**Status:** Accepted, amended 2026-10-17 (see the [Amendment](#amendment-2026-10-17-the-manual-apply-comes-after-v01))
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Phase 1 of [RFC-0004](../rfcs/0004-hosting-recipes.md). Each answer picks one of the two branches the RFC's [spike table](../rfcs/0004-hosting-recipes.md#the-first-phase-spike) names, and two decisions settle what the spike found beyond them.

## Context

RFC-0004 tests its AWS recipe against Floci, an AWS emulator, and lists what nothing had confirmed: ten questions, each with a branch for yes and one for no. Phase 1 asked each in a throwaway root against `floci/floci:2.2.0` (by digest, `sha256:e97cd0c1dc2aa14e7697fb5ef5018404c4d6345169dbd276315f0bed2c7b0520`), with OpenTofu 1.13.1 and the AWS provider at `~> 6.68`. Floci ran in Docker mode, with RDS's default image set to PostgreSQL 17.

## Decision

### The answers

| Item | Answer | Branch |
|---|---|---|
| `aws_db_instance` | PostgreSQL 17 with `manage_master_user_password` is created, plans again with no changes, and is destroyed. `psql` through the relay works. Floci's PostgreSQL has TLS off, and its master is a superuser | Yes |
| `aws_lb` and its rules | The HTTPS listener with an ACM certificate, the redirect from 80 and the host-header rules plan again with no changes. Requests route by Host, an unknown host gets the default 404, and `/admin/*` on `auth.<host>` is refused. The HTTPS listener answers plain HTTP: it holds the certificate but doesn't terminate TLS | Yes |
| `aws_ecs_service`, `aws_ecs_task_definition` | They plan again with no changes, and services reach a steady state | Yes |
| ECS secrets | A task gets a whole secret by ARN, and one key of a JSON secret (`<arn>:password::`) | Yes |
| ECS to RDS | A task reaches RDS's relay by the endpoint RDS reports | Yes |
| The state host | Floci's instance is a container that runs its user data, privileged, so Docker and Compose run inside it, on its EBS volume as a loop device. But it has no systemd, it loses the privilege when security groups are enforced, and tasks can't reach it at its private address | No: in `envs/floci`, its three services run on Fargate, without a volume |
| ElastiCache | The `noeviction` parameter group applies, and the auth token is enforced from creation. TLS isn't served, a changed token isn't applied, and `port` must be set, or every plan replaces the group | No: tier 2 runs without TLS, and the gap is checked at the manual gate |
| GoTrue on RDS | Its migrations grant to a `postgres` role, and fail where none exists. With one, they run as a role that isn't a superuser and owns only the `auth` schema | No: `db-init` creates a `postgres` role where there is none. The RDS master is named `postgres`, so on AWS it exists |
| GoTrue's admin JWT | `supabase/gotrue:v2.197.0`, the version the pinned Supabase CLI runs, signs with an ES256 key set in `GOTRUE_JWT_KEYS` and serves it at `/.well-known/jwks.json`. A service role JWT signed with that key is accepted on `/admin/users`; none is refused with 401. GoTrue still requires `GOTRUE_JWT_SECRET`, which gets a random value it never signs with | Yes |
| IAM enforcement | With `FLOCI_SERVICES_IAM_ENFORCEMENT_ENABLED`, an execution role whose policy omits a secret still gets it | No: IAM policies stay on the cannot-test list |

The generated secrets stay out of state: `secret_string_wo` and `auth_token_wo` leave only their versions there.

### Tier 2 runs without security-group enforcement

With `FLOCI_NETWORK_SECURITY_GROUP_ENFORCEMENT_ENABLED`, three things the recipe needs stop working:

- **Task roles:** the credential endpoint doesn't reach a task in a protected namespace, so Langfuse can't reach S3 with its role.
- **The load balancer:** its health checks and requests come from Floci's own container, not from the ALB's security group, so every target stays `initial`.
- **The state host:** its container loses the privilege Docker needs.

So tier 2 leaves it off, and security groups join IAM policies on the cannot-test list, checked at the manual apply on real AWS. Once, in the spike, enforcement held between tasks: a task outside the security group ClickHouse allows got no connection, and one inside it got an answer.

### The state host on Fargate, in `envs/floci` only

Production keeps the design: Compose under systemd on an EC2 instance with its own volume. `envs/floci` runs ClickHouse, Prometheus and prom-label-proxy as Fargate services instead, found through Cloud Map, as the spike's ClickHouse was. The instance, its user data, its volume and its systemd units run only at the manual gate.

### What else the recipe does

- **Instance sizes in `envs/floci` come from Floci's catalog.** It knows sizes up to `medium` (`t3.medium`, `t4g.medium`). It creates a `t4g.large`, but can't describe it, so every later refresh fails.
- **Tier 2 cleans up after Floci.** A destroy leaves Floci's VPC networks, `floci-aws-ec2-volume-helper`, and the containers that carried security groups. Tier 2 removes them, by their `floci-aws-` prefix, with Floci itself.
- **Tier 2 speaks HTTP to the HTTPS listener,** on 443, with each host's Host header, since Floci doesn't terminate TLS.
- **ElastiCache's port is a variable:** 6379 in `envs/prod`, and one in Floci's range in `envs/floci`.

### The cannot-test list, now

IAM policies, security groups, TLS at the edge, to RDS and to ElastiCache, a changed ElastiCache token, DNS validation of certificates, NAT egress, SSM port forwarding, the state host as built (EC2, its user data, systemd and its volume), Multi-AZ, EBS snapshots and DLM, rollouts across zones, and autoscaling. The manual apply on real AWS checks each before stackr's v0.1.

## Options considered

| Option | For | Against |
|---|---|---|
| **Tier 2 without enforcement (chosen)** | Task roles, the load balancer and the services work as the recipe builds them | Security groups are checked only at the manual gate |
| Enforcement, with a rule in `envs/floci` for Floci's network and static S3 keys for Langfuse | Security groups are checked in CI | `envs/floci` drifts from production in exactly what it would test |
| Two tier-2 runs, with and without | Both checked | Twice the time, for one half that needs the drift above |

## Consequences

- Easier: tier 2 tests the recipe as production builds it, except for the state host.
- Harder: security groups, and the state host as built, are checked by hand, at the gate.
- Revisit: enforcement, task roles and Docker in instances, when Floci makes them work together.

## Amendment (2026-10-17): the manual apply comes after v0.1

[lattice ADR-0023's amendment](../../adr/0023-publishing-to-pypi-from-the-release-workflow.md#amendment-2026-10-16) releases stackr's 0.1.0 without waiting for the manual apply on real AWS, and [RFC-0004's amendment](../rfcs/0004-hosting-recipes.md#amendment-2026-10-17-the-manual-apply-comes-after-v01) records it: the apply is a stated limit of v0.1, not its gate. What this ADR leaves to the apply (the cannot-test list) is still checked there, and only there, after the release. Where it says the apply comes before stackr's v0.1, or calls it a gate, this supersedes it.
