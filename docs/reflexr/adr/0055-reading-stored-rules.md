# ADR-0055: Reading stored rules: every pass, in their workspace, by namespace in metrics

**Status:** Accepted
**Date:** 2026-09-29
**Deciders:** Alex Nodeland

Amends [ADR-0018](0018-opentelemetry-observability-with-langfuse.md)'s cardinality policy, under which rule names may be metric attributes. Decided on [RFC-0003](../rfcs/0003-managing-rules-at-runtime.md).

## Context

With stored rules ([ADR-0053](0053-stored-rules-one-fixed-configuration.md)), a workspace's rules are no longer only the code's. Three things read rules and have to agree on them: the reactor, which evaluates and executes; the surfaces, which list them; and telemetry, which labels metrics with them.

- **The reactor.** Several reactors may serve one storage. A change has to reach all of them, and no process may run a replaced or archived version.
- **The surfaces.** `GET /v1/rules` and MCP's `list_rules` give every code rule to every authenticated client of any tenant, since code rules are the application's. A tenant's stored rules must never be listed to another tenant.
- **Metrics.** ADR-0018 allows rule names as metric attributes since code bounds them. Seven metrics carry `reflexr.rule`, at about 60 series per rule and workspace, so 1,000 workspaces with 20 stored rules each would add about 1.2 million series.

## Decision

- **One seam: `Workspaces.rules_in(workspace or transaction)`** returns a workspace's rules, the code rules and then its active stored rules in the configured namespaces, through the storage call or the transaction at hand. The reactor's passes, batches and claims, `replay_rule`, `rule_statuses` and `get_rule` read through it and nothing else.
- **No cache.** Every pass, batch and claim reads a workspace's stored rules, so a change takes effect by the next pass, within `serve()`'s poll interval.
- **A rule never sees its own changes.** `reflexr:rule_installed` and `reflexr:rule_archived` are facts about the rule, so it doesn't see them, as with its other facts ([ADR-0010](0010-loop-and-spend-safety.md)). Other rules can watch them: relayr does, to notice a change it didn't make.
- **Stored rules are read only in their workspace.** They are keyed by tenant and workspace, so no read can reach another tenant's:

| Read | REST | MCP |
|---|---|---|
| The code rules, for every tenant | `GET /v1/rules`, unchanged | `list_rules`, unchanged |
| Each of the workspace's rules' status, with its `origin` (`code` or `stored`) and `version` | `GET /v1/workspaces/{workspace_id}/rules` | `rule_status` |
| One rule's definition, and a stored rule's version and provenance | `GET /v1/workspaces/{workspace_id}/rules/{rule}` | `get_rule` |

- **Metrics record a stored rule as its namespace,** such as `chat:*`, which the configuration bounds. `reflexr.evaluation.lag` is a gauge, so for stored rules it records the most any rule of the namespace is behind. Code rules keep their qualified names, and the dashboards' queries don't change. A stored rule's detail is in its traces, in Langfuse and in the status read.
- **Operators' tools see stored rules' names.** Spans, Langfuse and LiteLLM metadata carry them; those are the operators', not the tenants'.

## Options considered

| Option | For | Against |
|---|---|---|
| **Read on every pass, batch and claim, through one lookup (chosen)** | No process runs a stale version, and nothing is invalidated | More reads: one primary-key read per pass, batch and claim |
| A cache per reactor, refreshed on a timer or by notification | Fewer reads | A replaced or archived version can run until the cache catches up |
| **The namespace as the metric label (chosen)** | Series bounded by configuration | Less detail in metrics for stored rules |
| Each stored rule's name as the label | Per-rule detail in dashboards | Series bounded only by tenants |
| No rule label for stored rules | Fewest series | Stored rules disappear from the dashboards |

## Consequences

- Easier: every reader sees the same rules, from wherever they came, and a change is live by the next pass on every reactor.
- Easier: no surface lists a stored rule to another tenant or workspace, by construction.
- Harder: every pass, batch and claim reads a workspace's stored rules.
- Harder: stored rules share a series per namespace, so a dashboard can't tell two apart.
- To revisit: per-rule metrics for stored rules, a tenant-level listing of rules, and a metric for what throttles drop.

## Action items

1. [x] `rules_in`, read by the reactor and the statuses, and the namespace as the metric label (alexnodeland/reflexr#88).
2. [x] `get_rule`, over REST and MCP (alexnodeland/reflexr#89).
