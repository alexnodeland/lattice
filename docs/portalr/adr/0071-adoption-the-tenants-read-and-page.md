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
  - **active people:** how many were active over the window, in its last 7 days and in its last 30, each ending where the window ends and within it (`uniqExact`);
  - how many people were active each day, in UTC;
  - each integration's uses and people, the 100 most used;
  - the funnel: people who viewed a page, then opened a thread, then sent a message, within 24 hours;
  - weekly retention: of the people active in the window's first week, how many were active in each whole week of it. A last week the window cuts short isn't counted, and neither is any week in a window shorter than one.
- **It is five queries, made one after another, within a 10-second deadline:**
  - One at a time, an adoption read takes one of the reader's four queries.
  - The reader's profile in stackr has `cancel_http_readonly_queries_on_client_close`, so a query cut off at the deadline is stopped and doesn't keep its slot. Checked on ClickHouse 26.9: without it, an abandoned read was still running a second later; with it, nothing was. stackr's smoke test checks that the reader has it.
  - **A partial answer is honest:** each part not read by the deadline is `null`, and `complete` is false. The page says that part wasn't read; it never shows 0 or "none" for it.
  - If ClickHouse refuses a query, or answers what portalr can't read, the whole answer is unavailable.
- **Each query is held to the tenant twice,** in `SQL_portalr_tenant` and in its own `WHERE`, each a parameter. The test that every read of the reader carries the tenant now covers this one. The two-tenant check in `scripts/smoke_analytics.py`, which stackr's smoke test runs, now reads each tenant's adoption too.
- **People are counted by their keyed hash,** never their id. Only people who said yes are there, and no event holds content. Events are kept for as long as the deployment sets, 395 days by default, so a window older than that is empty.
- **Admin's Adoption page** sits on the tenant's rail, after Runs and before Usage. It is loaded only when opened, so admin's first load is unchanged. Its window is in the address (7, 30 or 90 days), as Usage's is.
  - It shows the three active counts, a chart of people per day, and tables for integrations, the funnel and retention.
  - Unconfigured and unavailable each have a state of their own, in the kit's own words: the server's reason is for operators and never shown.
  - A BDD scenario checks the unconfigured state, as Usage's does. Admin's pages have no axe checks of their own; the page is built from the kit's components.

## Options considered

- **The queries at once:** five at once exceed the reader's four, as ClickHouse showed, and even four would leave no slot for another reader. Each takes milliseconds, so making them in turn costs little.
- **One query for everything:** each part groups differently, and one slow part would hold up the rest.
- **The page in the app:** adoption is for those who run the tenant, so it belongs in admin, beside Usage.

## Consequences

- A tenant's admins see how their people use the product without an operator.
- A partial answer leaves out the later parts, retention first. The page says which parts weren't read.
- Links from a session to its trace, and back, are [ADR-0073](0073-a-requests-analytics-session-on-its-trace.md)'s.
