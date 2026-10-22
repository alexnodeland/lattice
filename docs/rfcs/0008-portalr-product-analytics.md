# RFC-0008: portalr product analytics

**Status:** Draft
**Author:** Alex Nodeland
**Created:** 2026-10-22
**Discussion:** the pull request that adds this file; [#361](https://github.com/alexnodeland/lattice/issues/361)

## Summary

portalr records what people do in it as product events, in a database of its own on the ClickHouse that stackr already runs, and shows each tenant how its people adopt the product: active users, a funnel, weekly retention, and how much each integration is used. Operators read the same events across tenants in Grafana. Every event carries the trace and the browser session it belongs to, so a trace in portalr's admin links to the session that caused it, and back. Capture is opt-in per person, never automatic, and never holds content. The browser sends events only to a same-origin relay in portalr, which sets the tenant and workspace from the signed-in user. A tenant's reads go through a portalr reader that always filters by tenant, and ClickHouse row policies are a second wall behind it. Journeys and session replay come from Umami, an opt-in stackr profile fed by the same relay, with text masked and chat and artifact regions blocked; replay ships only after a privacy review.

## Motivation

Operators and tenants can't tell today whether a deployment is being used, by whom, or which integrations earn their place. The traces say what the system did (Tempo, Loki, Langfuse); nothing says what people did, or where they stopped. [#361](https://github.com/alexnodeland/lattice/issues/361) holds the research and the owner's first decisions (2026-10-17): native analytics on stackr's ClickHouse, Umami as an opt-in profile, replay linked to traces. Self-hosted PostHog was ruled out there: about 35 containers and 16 GB as its vendor states it, unsupported, untagged images, and no group analytics on self-host.

The constraints are lattice's own: a customer admin must never see another tenant's data ([portalr ADR-0006](../portalr/adr/0006-shared-stores-every-read-filtered.md)); the CSP stays `default-src 'self'`; images are pinned by version and digest; a local stack binds to 127.0.0.1; nothing phones home.

## What exists (checked against `main`, 2026-10-22)

- **ClickHouse** `26.9.20.23` is pinned in `packages/stackr/compose.yaml`, under `profiles: [langfuse]` only. Analytics today would need Langfuse to be on. Verified.
- **Its users** are `deploy/clickhouse/users.xml`'s ([stackr ADR-0031](../stackr/adr/0031-clickhouses-admin-apart-from-langfuse.md)): `admin` for operators, from inside the container; `langfuse` with `ALL` on `default` and `SELECT` on six system tables. Verified.
- **Backups** ([stackr ADR-0027](../stackr/adr/0027-the-single-hosts-backups.md), [ADR-0037](../stackr/adr/0037-the-state-hosts-clickhouse-backups.md)) take `BACKUP DATABASE default, DATABASE stackr_drill`. A new database is not backed up until the scripts name it. Verified.
- **Grafana** `13.2.2` runs under `profiles: [observability]` with four datasources (Prometheus, Tempo, Loki, Pyroscope) and none for ClickHouse. Verified.
- **portalr's readers** (`portalr.readers`) each filter by tenant, and `tests/readers/test_queries.py` fails if a trace, log, metric, score or spend query lacks the tenant. Verified.
- **The usage read** ([portalr ADR-0028](../portalr/adr/0028-usage-and-spend.md)) takes a window of at most 91 days, has a deadline and a partial flag, and answers `ok`, `unavailable` or `unconfigured`. The Adoption read follows its shape. Verified.
- **Langfuse session links:** `readers/langfuse.py` has `session_link(session_id)`. Verified.
- **The UIs' CSP** is `default-src 'self'` (`portalr/fastapi/ui.py`). Verified.
- **grantr removes a member** (`Grants.remove_member`). A hook that other packages run on removal is **unverified**; deletion by person may need one.
- **ClickHouse's licence** (Apache-2.0) and **`grafana/clickhouse-datasource`** (Apache-2.0, v4.23.1) are from upstream and **unverified** here.
- **Umami** v3.4.0 (MIT): the licence, replay since v3.1, and deep-linking a replay by session id are **unverified**, and are for phase 0.

## Design

### P1. The store: a database of portalr's own, on a ClickHouse of its own profile

- **ClickHouse gets its own profile**, `clickhouse`, which both `langfuse` and `analytics` pull in. The service is listed under all three (`profiles: [clickhouse, langfuse, analytics]`), as PostgreSQL is listed under several today. Analytics works without Langfuse, and Langfuse is unchanged (owner, 2026-10-22).
- **ClickHouse is the source of truth.** Umami, when it runs, is a second consumer of the relay's events, never the record.
- **One database, `analytics`, holds one table to start, `events`,** partitioned by `toYYYYMM(ts)`, ordered by `(tenant_id, workspace_id, event, ts)`, with a `TTL` (P5).
- **Two users join `admin` and `langfuse`:**
  - `portalr_analytics_writer`: `INSERT` on `analytics.events` and nothing else.
  - `portalr_analytics`: `SELECT` on `analytics.events`, behind a row policy (P4).
  - Neither reaches `default` or Langfuse's tables, and `langfuse` doesn't reach `analytics`.
- **Writes are batched,** with ClickHouse's async inserts or a small buffer in the relay. Which one is for phase 0, from measurements.
- **Backups name `analytics`** beside `default` and the drill's database, on the single host and the state host, and the drill restores it too.

The `events` table, a `MergeTree`:

| Column | Type | Is |
|---|---|---|
| `ts` | `DateTime64(3, 'UTC')` | When the event happened, by the server's clock |
| `tenant_id` | `LowCardinality(String)` | Set by the relay or the server, never by the browser |
| `workspace_id` | `String` | Likewise; empty where the event is a tenant's |
| `distinct_id` | `FixedString(32)` | A keyed hash of the user id (P5) |
| `event` | `LowCardinality(String)` | A name from the registry (P6) |
| `trace_id` | `FixedString(32)` | The server span's, where there is one |
| `session_id` | `String` | The browser session's, where there is one |
| `actor_kind` | `LowCardinality(String)` | `user`, `principal` or `agent` |
| `props` | `Map(LowCardinality(String), String)` | The registry's allowed keys only |

### P2. Capture: a same-origin relay and a server-side helper

- **`POST /portalr/v1/events`** is same-origin and needs the signed-in user's token, so the CSP stays `'self'` and no third-party script loads.
- **What the relay does to each event:**
  - checks consent (P3) and drops the event without it;
  - checks the name against the registry (P6) and drops any key the registry doesn't allow;
  - overwrites `tenant_id` and `workspace_id` from the session;
  - stamps `distinct_id` (P5) and the server's `ts`;
  - writes nothing it was not given, keeps no IP, and reduces the user agent to a coarse class (`desktop`, `mobile`, `tablet`).
- **The server-side helper** (`portalr.analytics.capture`) records server events, such as an integration used or a proposal applied, with the request's `trace_id`, under the same rules. It is portalr's. It moves into a lattice-core extra only when a second package needs it.
- **Browser capture** is a small, lazy-loaded module with its own size ceiling ([portalr ADR-0040](../portalr/adr/0040-scenarios-against-a-generated-application-and-size-budgets.md)). It sends named events only: no autocapture, no DOM snapshots.
- **Correlation:** the browser session id is set on portalr's spans as `session.id` (the OpenTelemetry attribute; its stability is **unverified**), and server events carry `trace_id`. Traces stay in Tempo, Loki and Langfuse. No span, log or `$ai_*` data is sent to analytics, and the two are joined only by `trace_id` and session id.

### P3. Consent

- **Opt-in per person,** with the deployment's default `opt_in` (nothing is captured until a person agrees). The choice is stored server-side, per user and deployment, and the relay reads it on every event.
- **A person can change it any time,** in the account menu, as colour-blind mode is set today. Withdrawing stops capture at once, and asks for their past events to be deleted (P5).
- **Replay** (P8) needs its own, separate consent, on top of analytics consent.
- **The consent UI** follows the kit and is accessible: keyboard, screen reader, both schemes, and colour-blind mode.

### P4. Isolation: the reader is the wall, row policies the second

- **The tenant wall is portalr's `analytics` reader.** It takes a `Tenant` and puts `tenant_id = {tenant}` first in every query it builds, as its siblings do. A test in `test_queries.py` fails if any analytics query lacks it.
- **The second wall is a ClickHouse row policy** on `portalr_analytics`, so a reader bug can't read across tenants. The reader sets a custom setting on each query (`SETTINGS SQL_portalr_tenant = '…'`), and the policy below holds its rows to it. The setting is set by the query, so the policy guards against a missing filter, not against a hostile query string; it is a wall only as far as the reader can't be made to set another tenant's id.
- **This row-policy-by-setting pattern is unverified on 26.9.** Phase 0 settles it with an experiment in the first slice's test:
  1. Configure `custom_settings_prefixes` for `SQL_`.
  2. Make the policy, and insert rows for two tenants.
  3. As `portalr_analytics`, show:
     - a query with the setting for tenant A sees only A's rows;
     - with no setting, it sees none, or fails;
     - it can't change the setting by `SET` within a readonly profile, if `readonly=2` allows only the query-level setting (to measure);
     - `system.query_log` shows the setting, for audit.
- **If the pattern fails,** the fallback is a ClickHouse user per tenant made by portalr (heavier), or the reader alone, with the decision recorded.
- **Operators read across tenants** in Grafana, as `admin` or a read-only `grafana_analytics` user with no row policy. [portalr ADR-0005](../portalr/adr/0005-operators-see-across-tenants.md) allows this.
- **Two-tenant acceptance tests** ([portalr ADR-0012](../portalr/adr/0012-acceptance-against-a-two-tenant-stack.md)) show tenant A's Adoption page never counts B's events.

The row policy:

```sql
CREATE ROW POLICY tenant_wall ON analytics.events
  USING tenant_id = getSetting('SQL_portalr_tenant') TO portalr_analytics
```

### P5. Retention and deletion

- **Default retention is 395 days** (13 months, so a year can be compared with the one before), as a table `TTL`.
- **The operator sets it per deployment** (`PORTAL_ANALYTICS_RETENTION_DAYS`). Tenants can't shorten it in v1 (owner, 2026-10-22).
- **`distinct_id` is `HMAC-SHA-256(key, user_id)`,** truncated to 128 bits and kept hex. Analytics never holds the raw user id, and a person's events can still be found and deleted by computing the hash. The key's scope (per deployment or per tenant) is an open question.
- **Deletion:**
  - a person: `DELETE FROM analytics.events WHERE distinct_id = …` (a lightweight delete), when they withdraw consent or are removed;
  - a tenant: by `tenant_id`.
- How a lightweight delete behaves on 26.9 (visibility before the merge, cost) is **unverified**, for phase 0. Running it on grantr's member removal needs a removal hook, which is also **unverified** (see "What exists").

### P6. Taxonomy

- **Names are namespaced and versioned:** `<surface>.<object>.<action>.v<N>`, for example `app.thread.opened.v1` or `integration.used.v1`.
- **The registry** (`portalr/analytics/events.json`) lists each event and the `props` keys it may carry. The relay drops the rest, and a test fails on an event sent from code that isn't in it.
- **What events carry:** server events have `trace_id`, actor kind, integration key and outcome; browser events have route, component and session id.
- **Never:** message or artifact content, file names, emails, keys, free text, or IPs.
- **Per-integration adoption is a first-class report:** the tracker, native files, forms, Excalidraw and the Markdown add-ons. Mapping artifactr's, reflexr's and relayr's own event types onto the taxonomy is **unverified**, for phase 0.

### P7. Reading: the Adoption page and Grafana

- **`GET /portalr/v1/adoption`**, shaped like the usage read: a window of at most 91 days, a deadline, a partial flag, and `ok`, `unavailable` or `unconfigured`. It holds active users (daily, weekly, monthly), per-integration adoption, one funnel, and weekly retention, from ClickHouse's `uniq`, `windowFunnel` and `retention`.
- **An Adoption page** in admin, for whoever may read the tenant's usage, with charts on the existing palette tokens.
- **Operators get Grafana:** a pinned `grafana/clickhouse-datasource` and one dashboard across tenants. Recorded deep links to it, and to Umami, go on the Tools page, as Langfuse's and Grafana's links do today. No iframes.

### P8. Umami and session replay (an opt-in profile)

- **stackr gets an `umami` profile,** off by default:
  - the image pinned by version and digest, Renovate-managed;
  - bound to 127.0.0.1 locally, and reached through the edge on a host;
  - telemetry off.
- **Umami's ingest is unauthenticated,** so it is reachable only from portalr's relay, on an internal network with no published port. The relay forwards consented events to it.
- **Replay is in the first release, behind this profile** (owner, 2026-10-22). Masking is the main risk, so these hold:
  - **Masking:** all text is masked by default. Inputs are never recorded. The chat, artifact, native file, form and dashboard regions are blocked whole (`data-analytics-block`), and so are mini apps' frames. Admin's Access pages are never recorded.
  - **Consent:** separate from analytics consent, opt-in, per person, and withdrawable, which deletes that person's recordings.
  - **Links:** a replay links to its traces by `session.id`, and a trace links to its replay. Whether a replay can be opened by session id in Umami is **unverified**, for phase 0. If it can't, ClickStack (HyperDX) is the fallback to look at again.
  - **Retention:** no longer than analytics' own, and shorter if the review asks.
  - **Exit criterion:** a privacy review of replay signs off before replay is turned on in any release. It covers the masking rules against every route in both UIs (a screenshot of each, masked), the consent flow, the retention, and where the recordings are kept. Without it the profile ships with replay off.

## Phases

About 8 to 9 PRs, batched where they share a review:

0. **This RFC and a stackr ADR** amending ADR-0031: the `clickhouse` profile, the analytics users, and backups. Docs only.
1. **The first slice** (one PR, below).
2. **Relay, consent and browser capture:** `POST /portalr/v1/events`, the registry, the consent setting and UI, and the lazy capture module with its size ceiling.
3. **Operators' view:** the Grafana ClickHouse datasource and one dashboard.
4. **Adoption:** `GET /portalr/v1/adoption` and the Adoption page (two PRs: the read, then the page).
5. **Traces both ways:** `session.id` on spans, and the links from a trace to its session and back.
6. **Umami:** the profile and the relay's forwarding, then replay with its masking and consent behind the privacy review (two PRs).
7. **relayr's sink** (optional): counts and kinds of lattice events, never content.

### The first slice

One PR, with no browser capture and no UI:

1. the `analytics` database, the `events` table, and the two users, in `users.xml` and an init step; the `clickhouse` profile; backups naming the database;
2. one server-side event, `integration.used.v1`, from an existing action;
3. the `analytics` reader, with the test that every query carries the tenant;
4. a two-tenant test: A's reads never see B's rows, through the reader and through the row policy (the phase 0 experiment above);
5. cost measurements, in the PR and the ADR:
   - rows per second inserted;
   - compressed bytes per row;
   - a 90-day funnel for one tenant;
   - the ClickHouse container's memory with and without Langfuse.

## Drawbacks

- Langfuse and analytics share one ClickHouse's CPU, memory and disk. A heavy funnel can slow Langfuse's writes, so each user gets a quota.
- One more profile, and one more database to back up, restore and drill.
- A row policy keyed on a setting is unusual, and it depends on a setting the reader sets itself.
- Umami has a small maintainer base, so the native pipeline stays the record.
- Replay is a privacy risk however well it is masked: it ships behind a review, consent, and an opt-in profile.

## Alternatives

| Option | Licence | Self-host | Isolation | Verdict |
|---|---|---|---|---|
| **Native on stackr's ClickHouse (chosen)** | Apache-2.0 (unverified) | No new container where ClickHouse runs | Reader, plus row policies | The record |
| **Umami profile (chosen, opt-in)** | MIT (unverified) | One container on PostgreSQL | By website, not tenant: operators only | Journeys and replay |
| Plausible CE | AGPL-3.0 | Its own PostgreSQL and ClickHouse | No tenant model | No: AGPL, no replay |
| Self-hosted PostHog | Mixed, `ee/` its own | About 35 containers, 16 GB (vendor) | Event properties only | No: [#361](https://github.com/alexnodeland/lattice/issues/361) |
| Langfuse | In the stack | Running | LLM traces, not product events | Traces only |
| OTel span events and logs into Loki | n/a | Nothing new | The existing tenant filter | No: funnels and retention are poor on Loki |

## Not doing

- **These tools:**
  - self-hosted PostHog;
  - OpenPanel (its public images stopped updating, and v3 is paid);
  - Snowplow (its licence forbids self-hosting in production);
  - RudderStack (Elastic License);
  - Matomo (funnels and replay are paid plugins);
  - Countly (MongoDB, and a branding clause);
  - Highlight (shut down 2026-02-28).
- **ClickStack (HyperDX),** unless linking replays to traces in Umami proves impossible in phase 0.
- **Feature flags.** The per-workspace Integrations switch stays grantr's port ([RFC-0006](0006-excalidraw-diagrams-drawn-live.md)); an external flag provider could only narrow it.
- **Autocapture,** DOM snapshots outside replay, and any content in events.
- **Tenants shortening retention** in v1, and a tenant's own replay viewer.
- **Iframes** of Grafana or Umami in portalr.
- **Sending traces, logs or `$ai_*` data** to the analytics store.

## Unresolved questions

Decided by the owner (2026-10-22):

- ClickHouse gets its own profile.
- Retention is 395 days by default, set per deployment, with no tenant shortening in v1.
- Replay is in v1, behind Umami.
- Native ClickHouse is the record, with the reader and row policies as two walls.

Still open:

1. **The `distinct_id` hashing key: per deployment or per tenant?**
   - Per deployment: one person's events across tenants can be deleted with one hash.
   - Per tenant: their events in two tenants can't be joined, even by an operator.
2. **Umami's PostgreSQL:** a schema in the stack's shared PostgreSQL, or a PostgreSQL of its own? Sharing is lighter. A database of its own keeps a third-party tool's migrations and replay storage away from Supabase's and LiteLLM's.
3. **Grafana's ClickHouse plugin:** baked into the `stackr-grafana` image, or installed when Grafana starts? Baking it is pinned and offline. Installing at start needs the network and a pin in the environment.
4. Whether the row-policy-by-setting pattern holds on 26.9 (phase 0's experiment).
5. How lightweight deletes behave on 26.9, and whether grantr needs a removal hook for them.

## Tracking

- [ ] Phase 0: this RFC and [stackr ADR-0044](../stackr/adr/0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md)
- [ ] The first slice
- [ ] Relay, consent and browser capture
- [ ] Grafana's datasource and dashboard
- [ ] Adoption read and page
- [ ] Traces both ways
- [ ] Umami profile, then replay after the privacy review
- [ ] relayr's sink
