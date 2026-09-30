# ADR-0041: Dashboards generated, tested and released

**Status:** Accepted; its release assets superseded by [ADR-0054](0054-dashboards-from-the-checkout.md)
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

### Amendment (2026-09-29): as stackr runs them

reflexr's port of these dashboards, run against stackr's Prometheus and Grafana ([reflexr ADR-0038](https://github.com/alexnodeland/reflexr/blob/main/docs/adr/0038-dashboards-generated-tested-and-released.md)), found three problems that artifactr's dashboards had too:

- **The release asset is `artifactr-dashboards-<version>.tar.gz`**, with the tag's `v` left out: the archive stackr's `scripts/fetch-dashboards` downloads from the release tagged `v<version>`. stackr would never have found the `artifactr-grafana-dashboards-<tag>.tar.gz` bundle above. The workflow still attaches each dashboard file too, and still creates no releases or tags.
- **Every query has a one-minute min step.** The OpenTelemetry SDK exports metrics once a minute by default, and stackr's data source leaves Grafana's scrape interval at 15 seconds, so `$__rate_interval` came out at one minute: most windows held one sample, and rate panels showed "No data". With the min step, Grafana makes `$__rate_interval` at least four minutes, so every rate spans several exports.
- **`$job`'s "All" is the services artifactr's metrics come from** (those that record `artifactr.commands`), not `.*`. The external metrics' names are shared: stackr's LiteLLM proxy records `gen_ai.client.token.usage` too, and every FastAPI or SQLAlchemy service records the HTTP and database pool metrics, so "All" added other services' tokens, requests and connections to artifactr's. `$tenant` and `$workspace` keep `.*`, which also matches series without the label.

The test now also checks that every query has the min step, that `$job`'s "All" is not `.*`, and that every legend names only labels its query groups by. It runs the workflow's packaging step, and checks the archive's name against stackr's and that stackr's filter finds every dashboard in it.

To revisit: a deployment that exports metrics less often than once a minute needs a longer min step. stackr's data source could declare the export interval as its scrape interval instead, for every library's dashboards.

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
2. [x] The archive name stackr fetches, the one-minute min step and `$job`'s "All", with tests (2026-09-29).
