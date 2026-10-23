# ADR-0048: Grafana's ClickHouse data source and the adoption dashboard

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Amends [ADR-0044](0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md) for phase 3 of [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) (portalr product analytics, [#361](https://github.com/alexnodeland/lattice/issues/361)): operators read portalr's analytics across tenants in Grafana.

## Context

- **Grafana had no ClickHouse data source.** ClickHouse's isn't one of Grafana's own; it is a plugin, `grafana-clickhouse-datasource`, which Grafana would otherwise download as it starts.
- **Compose ran upstream Grafana with mounts,** and the AWS recipe ran `stackr-grafana`, a thin image with the same files baked in ([ADR-0035](0035-the-thin-images.md)). A plugin in one would not be in the other.
- **ClickHouse's analytics users are tenant-bound:** `portalr_analytics` sees only the tenant its setting names. Operators read across tenants ([portalr ADR-0005](../portalr/adr/0005-operators-see-across-tenants.md)), as RFC-0008 planned with a `grafana_analytics` user.

## Decision

- **`stackr-grafana` carries the plugin, and Compose builds that image.** `deploy/grafana/Dockerfile` fetches version 4.22.1 as the image is built, one archive per architecture, each checked against its sha256, and unpacks it outside `/var/lib/grafana`, so the data volume doesn't hide it. One machine and the AWS recipe run the same image; Compose's mounts keep the checkout's dashboards and provisioning live.
  - The plugin is signed by Grafana Labs, and Grafana checks the signature as it loads it. No unsigned plugin is allowed.
  - Nothing is downloaded when Grafana starts: the plugin is in the image, and preinstalled plugins are turned off.
  - `deploy/build-images` checks that the plugin loads with a valid signature. Renovate doesn't track the plugin's version; it moves by hand, with both digests.
- **`grafana_analytics` reads `analytics.events`, every tenant's, and nothing else.** It has `SELECT` on that table only, and no row policy, so no setting to name a tenant.
  - Its profile is read-only (`readonly` 2, since the plugin sends settings of its own), logs no query, and has the reader's limits as ceilings it may lower but not raise. The time limit's ceiling is 30 seconds, not the reader's 10: the plugin asks for a little more than the data source's 10-second query timeout.
  - Its password is `CLICKHOUSE_GRAFANA_PASSWORD`, which `make env` generates.
- **The data source is `analytics`,** provisioned beside the others, at `CLICKHOUSE_ADDRESS` over HTTP.
- **One dashboard, Adoption** (`stackr-adoption`), across tenants or for the ones chosen: active people by day, people per integration, the funnel from a page to a thread to a message, and weekly retention. People are counted by their keyed hash, never their id, and only people who said yes are there.

### Who reaches it

The cross-tenant read is for operators, by design (portalr ADR-0005). Grafana is never exposed to tenants:

- **On one machine,** Grafana is published on `STACKR_BIND`, `127.0.0.1` by default ([ADR-0006](0006-networks-and-published-ports.md)).
- **On a single host,** on `127.0.0.1` alone, reached by an SSH tunnel; Caddy doesn't route to it ([stackr RFC-0004](../rfcs/0004-hosting-recipes.md)).
- **On AWS,** by SSM port forwarding through the state host. The AWS recipe doesn't run analytics yet (ADR-0044), so its Grafana's `analytics` data source has nowhere to read.

portalr links no tenant to Grafana: its deep links go only to callers allowed `portalr:read_deployment`, which only operators hold.

## Options considered

- **Download the plugin as Grafana starts** (`GF_PLUGINS_PREINSTALL`): each start would need the network and grafana.com, and the version wouldn't be checked against a digest.
- **Bake the plugin only into the AWS image:** one machine would run a different Grafana from the one deployed.
- **Read as `admin`:** an operator's dashboard would hold the password that may change anything.
- **`portalr_analytics` with a tenant per panel:** a dashboard across tenants is the point.

## Consequences

- Compose builds Grafana's image the first time it starts, from lattice's checkout.
- A plugin release is a hand-made change: its version and its two digests.
- The smoke test checks that Grafana's user reads both tenants and is refused an insert, `system.query_log` and any higher limit, and, with Grafana running, that the data source is healthy and the dashboard is there.
