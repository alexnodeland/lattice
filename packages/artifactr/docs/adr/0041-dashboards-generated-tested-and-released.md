# ADR-0041: Dashboards generated, tested and released

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

[RFC-0002](../rfcs/0002-observability-feedback-and-evaluation.md) ships Grafana dashboards in `deploy/grafana/dashboards/`: an overview, a tenant, a workspace, the agent and LLM, collaboration, surfaces and storage. A test checks that every query refers to a metric in the registry, and each release publishes them for stackr to provision by version ([ADR-0030](0030-compose-and-dev-containers.md)). How the dashboards are written, what the test checks beyond metric names, and how they are published were left open.

Grafana's dashboard JSON is long and repetitive, and hand edits to it drift: a panel's data source, units or template variables end up differing between dashboards.

## Decision

- **The dashboards are generated** by `scripts/grafana_dashboards.py` (`make dashboards`), which builds every panel from a few helpers:
  - data source uid `prometheus`, as stackr provisions it
  - `$job`, `$tenant` and `$workspace` variables down to each dashboard's scope
  - rates over `$__rate_interval`
  - exemplars on latency panels, which link to traces

  The JSON files are checked in, and a test fails if they differ from the script's output.

- **The test checks every query:**
  - its series are Prometheus names of registry metrics (artifactr's own, or the external ones the registry lists), as the OTLP translation writes them
  - for artifactr's metrics, every label it matches or groups by is an attribute the registry declares, or a resource label
  - the query parser itself is tested against queries that must fail
- **Release assets:** when a release is published, a workflow attaches each dashboard file and a `artifactr-grafana-dashboards-<tag>.tar.gz` bundle to it. It can also be run by hand for an existing release. It never creates releases or tags.
- CI checks the files are valid JSON without starting Grafana.

## Options considered

| Option | Drift between dashboards | Drift from the registry |
|---|---|---|
| **Generated from a script, tested against the registry (chosen)** | None: one set of helpers | Caught for metrics and labels |
| Hand-written JSON, tested for metric names | Likely | Caught for metric names only |
| Grafana's Foundation SDK, or Grafonnet | None | Needs the same test, and another toolchain |

## Consequences

- Easier: a new panel is a few lines; a renamed metric or attribute fails a test until the dashboards follow.
- Easier: stackr provisions the dashboards of the version it pins.
- Harder: dashboards edited in Grafana's UI must be carried back into the script.

## Action items

1. [x] Seven dashboards, the tests, CI's JSON check and the release workflow.
