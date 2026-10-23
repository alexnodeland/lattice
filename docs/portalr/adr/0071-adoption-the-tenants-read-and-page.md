# ADR-0071: Adoption, the tenant's read and page

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Implements the tenant's view in phase 4 of [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md) (portalr product analytics, [#361](https://github.com/alexnodeland/lattice/issues/361)). It follows the shape of [ADR-0028](0028-usage-and-spend.md), usage and spend.

## Context

- **portalr records product events** in ClickHouse, from people who said yes ([stackr ADR-0044](../../stackr/adr/0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md)), and its reader already reads one tenant's counts. Operators see adoption across tenants in Grafana ([stackr ADR-0048](../../stackr/adr/0048-grafanas-clickhouse-data-source-and-the-adoption-dashboard.md)). A tenant had no view of its own.
- **The reader, `portalr_analytics`, is held to one tenant twice:** by the row policy's setting and by each query's own filter. It may run four queries at once.

## Decision

- **`GET /portalr/v1/adoption`** answers a tenant's adoption over a window of at most 91 days. It answers ok, unavailable or unconfigured, as every read does, and needs `portalr:read_telemetry` on the tenant. The answer has:
  - how many people were active, and how many each day, in UTC;
  - each integration's uses and people;
  - the funnel: people who viewed a page, then opened a thread, then sent a message, within a day;
  - weekly retention: of the people active in the window's first week, how many were active in each week of it.
- **It is four queries, made one after another, within a 10-second deadline.** One at a time, an adoption read takes one of the reader's four queries. The reads not made by the deadline are left out, empty rather than 0, and the answer says it is partial (`complete: false`). A query ClickHouse refuses makes the whole unavailable.
- **Each query is held to the tenant twice,** in `SQL_portalr_tenant` and in its own `WHERE`, each a parameter. The test that every read of the reader carries the tenant now covers this one. The two-tenant check in `scripts/smoke_analytics.py`, which stackr's smoke test runs, now reads each tenant's adoption too.
- **People are counted by their keyed hash,** never their id. Only people who said yes are there, and no event holds content.
- **Admin's Adoption page** sits on the tenant's rail beside Traces and Logs. It is loaded only when opened, so admin's first load is unchanged. Its window is in the address (7, 30 or 90 days), as Usage's is.
  - It shows the window's people, a chart of people per day, and tables for integrations, the funnel and retention.
  - Unconfigured and unavailable each have a state of their own, in the kit's own words: the server's reason is for operators and never shown.

## Options considered

- **The four queries at once:** they would take every one of the reader's four queries, so a second reader could be refused. They take milliseconds each, so making them in turn costs little.
- **One query for everything:** each part groups differently, and one slow part would hold up the rest.
- **The page in the app:** adoption is for those who run the tenant, so it belongs in admin, beside Usage.

## Consequences

- A tenant's admins see how their people use the product without an operator.
- A partial answer leaves out the later parts: retention first, then integrations.
- Links from a session to its trace, and back, follow in their own record.
