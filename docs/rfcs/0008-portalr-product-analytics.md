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

- **ClickHouse gets its own profile**, `clickhouse`, which both `langfuse` and `analytics` pull in. The service is listed under all three (`profiles: [clickhouse, langfuse, analytics]`), as `db-init` is listed under `[langfuse, gateway, auth]` today. Analytics works without Langfuse, and Langfuse is unchanged (owner, 2026-10-22).
- **ClickHouse is the source of truth.** Umami, when it runs, is a second consumer of the relay's events, never the record.
- **One database, `analytics`, holds one table to start, `events`,** partitioned by `toYYYYMM(ts)`, ordered by `(tenant_id, workspace_id, event, ts)`, with a `TTL` (P5).
- **Two users join `admin` and `langfuse`:**
  - `portalr_analytics_writer`: `INSERT` on `analytics.events` and nothing else.
  - `portalr_analytics`: `SELECT` on `analytics.events`, behind a row policy (P4).
  - Both sign in only from the stack's internal network, where the application runs, not from `::/0` as `langfuse` does, and not from outside.
  - Neither reaches `default` or Langfuse's tables, and `langfuse` doesn't reach `analytics`.
- **Writes are batched,** with ClickHouse's async inserts or a small buffer in the relay. Which one is for phase 0, from measurements.
- **Backups name `analytics`** beside `default` and the drill's database, on the single host and the state host. The `backup` user's grants (`deploy/host/clickhouse/backup-user.xml`, today `SELECT, BACKUP ON default.*`) grow to `analytics.*`, or the scripts' statement is refused. The drill restoring it needs grants on the databases it restores into (stackr ADR-0044).

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

- **`POST /portalr/v1/events`** is on the portal's own origin, so the browser sends to no other and the CSP stays `'self'`; it needs the signed-in user's bearer token, not a cookie, so another site's page can't send under a person's name. It caps a request's body, the events in it, and each `props` value's length, and is rate-limited per person.
- **The relay mints the session id,** or binds the browser's to the signed-in user with an HMAC, so a browser can't attach its events or replays to another person's session.
- **A route is the router's template,** such as `/t/$tenant/w/$workspace/threads/$thread`, never the raw path or its query string, which can hold ids and search text.
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

- **The tenant wall is portalr's `analytics` reader.** It takes a `Tenant` and puts `tenant_id = {tenant:String}` in every query it builds, as its siblings do. A test in `tests/readers/test_analytics.py` fails if any of the reader's reads, each listed there, sends a query without it, or without the row policy's setting.
- **The second wall is a ClickHouse row policy** on `portalr_analytics`, so a reader bug can't read across tenants. The reader sets a custom setting on each query (`SETTINGS SQL_portalr_tenant = '…'`), and the policy below holds its rows to it. The setting is set by the query, so the policy guards against a missing filter, not against a hostile query string; it is a wall only as far as the reader can't be made to set another tenant's id.
- **This row-policy-by-setting pattern held on ClickHouse 26.9.20.23** (the first slice's experiment, below). The plan was:
  1. Configure `custom_settings_prefixes` for `SQL_`.
  2. Make the policy, and insert rows for two tenants.
  3. As `portalr_analytics`, show:
     - a query with the setting for tenant A sees only A's rows;
     - with no setting, it sees none, or fails;
     - it can change that one setting and no other: a readonly profile (`readonly = 1`) with the tenant setting alone `changeable_in_readonly`, so a read can't lift its memory or time limits, or turn logging on;
     - who can see the setting in `system.query_log`; as built, no analytics query is logged at all (below), so audit of reads is portalr's to keep.
- **Had the pattern failed,** the fallback was a ClickHouse user per tenant made by portalr (heavier), or the reader alone.
- **`system.query_log` is readable by `langfuse`** (ADR-0031 granted it, to follow its own queries' progress), so it could read analytics' query text: tenant ids, `distinct_id` hashes, and an insert's values where they are inline. stackr ADR-0044 closes it three ways:
  - a row policy on `system.query_log` and `system.processes` limits `langfuse` to its own queries;
  - analytics' queries aren't logged (`log_queries = 0`, which they can't change);
  - `query_masking_rules` redact the tenant setting and the `tenant_id` and `distinct_id` literals of any statement that is logged (as built, below).
  - the relay sends inserts' rows in the request body, not the query text.
- **The reader can still name any tenant in the setting.** ClickHouse can't refuse one tenant id for another, so the setting guards against a missing filter, not a reader that names the wrong tenant. A query whose `WHERE` and setting disagree sees nothing.
- **Operators read across tenants** in Grafana, as `admin` or a read-only `grafana_analytics` user with no row policy. [portalr ADR-0005](../portalr/adr/0005-operators-see-across-tenants.md) allows this.
- **Two-tenant acceptance tests** ([portalr ADR-0012](../portalr/adr/0012-acceptance-against-a-two-tenant-stack.md)) show tenant A's Adoption page never counts B's events.

The row policy:

```sql
CREATE ROW POLICY tenant_wall ON analytics.events
  USING tenant_id = getSetting('SQL_portalr_tenant') TO portalr_analytics
```

### P5. Retention and deletion

- **Default retention is 395 days** (13 months, so a year can be compared with the one before), as a table `TTL`.
- **The operator sets it per deployment** (stackr's `ANALYTICS_RETENTION_DAYS`, which `clickhouse-init` sets as the table's TTL each time `make up` starts the analytics profile). Tenants can't shorten it in v1 (owner, 2026-10-22).
- **`distinct_id` is `HMAC-SHA-256(key, user_id)`,** truncated to 128 bits and kept hex. Analytics never holds the raw user id, and a person's events can still be found and deleted by computing the hash. The key is **per deployment** (owner, 2026-10-22), so one person's events across tenants are deleted with one hash.
- **A known trade-off of a per-deployment key:** the same person has the same `distinct_id` in every tenant, so an operator, who reads across tenants, can link one person's use of several tenants. Tenants can't, since each sees only its own rows. The owner chose per deployment for one-hash deletion (2026-10-22).
- **The key is a secret of the deployment's,** `PORTAL_ANALYTICS_KEY`, which the template's `make env` will generate once analytics is wired into a generated application (the next phase), held as the other secrets are, and never in ClickHouse. Rotating it breaks deletion by person for the events hashed under the old key, so a rotation either keeps the old key to delete with until its events age out under the TTL, or re-keys the table by a mutation; which one is for the ADR that adds the key. It is never rotated silently.
- **Backups keep deleted persons' events** until the bucket's lifecycle rule expires the backups that hold them. A deletion is not retroactive in a backup, and the operator's guide says so, with the backups' retention.
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
- **Umami's ingest is unauthenticated,** so it is reachable only from portalr's relay: Umami is on a network it shares only with portalr's application, with no published port. The relay forwards consented events to it.
- **Replay is in the first release, behind this profile** (owner, 2026-10-22). Masking is the main risk, so these hold:
  - **Masking:** all text is masked by default. Inputs are never recorded. The chat, artifact, native file, form and dashboard regions are blocked whole (`data-analytics-block`), and so are mini apps' frames. Admin's Access pages are never recorded.
  - **Consent:** separate from analytics consent, opt-in, per person, and withdrawable, which deletes that person's recordings.
  - **Links:** a replay links to its traces by `session.id`, and a trace links to its replay. Whether a replay can be opened by session id in Umami is **unverified**, for phase 0. If it can't, ClickStack (HyperDX) is the fallback to look at again.
  - **Retention:** no longer than analytics' own, and shorter if the review asks.
  - **The relay to Umami** strips `X-Forwarded-For` and the user agent, and sends events from portalr's own address, so Umami sees no person's network or browser. It checks replay consent server-side on every replay payload, caps each payload's size, and is rate- and body-limited per person, as the events route is.
  - **Exit criterion:** a privacy review of replay signs off before replay is turned on in any release. It covers the masking rules against every route in both UIs (a screenshot of each, masked), the consent flow, the trace links (the `session.id` join between a replay and its traces, and who can follow it either way), the retention, and where the recordings are kept. Without it the profile ships with replay off.

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

1. the `analytics` database, the `events` table, and the two users, in `users.xml` and an init step; the `clickhouse` profile, with `langfuse` never left with an empty password; backups naming the database, with the `backup` user's grants on it and the drill's on its scratch database; the `query_masking_rules` for `analytics.`;
2. one server-side event, `integration.used.v1`, from an existing action;
3. the `analytics` reader, with the test that every query carries the tenant;
4. a two-tenant test: A's reads never see B's rows, through the reader and through the row policy (the phase 0 experiment above);
5. cost measurements, in the PR and the ADR:
   - rows per second inserted;
   - compressed bytes per row;
   - a 90-day funnel for one tenant;
   - the ClickHouse container's memory with and without Langfuse.

## First slice as built

- **The stack.**
  - ClickHouse runs under `profiles: [clickhouse, langfuse, analytics]`.
  - `clickhouse-init`, which `make up` runs with `docker compose run` once ClickHouse is up (so `up --wait` waits on nothing that exits), makes `analytics.events` as `admin`, from inside ClickHouse's network namespace, and sets the TTL from `ANALYTICS_RETENTION_DAYS` (395).
  - The two users are in `deploy/clickhouse/analytics-users.xml`, and the server settings (`custom_settings_prefixes`, `query_masking_rules`) in `deploy/clickhouse/analytics.xml`.
  - ClickHouse's HTTP interface is published on `127.0.0.1` only (`CLICKHOUSE_HTTP_PORT`, 8123), whatever `STACKR_BIND` says, for an application on this machine.
- **The row policy** is the user's own, in `analytics-users.xml` (`<databases><analytics><events><filter>`), not a `CREATE ROW POLICY` statement: it is reviewed with the code, as ADR-0031's users are.
- **The reader's profile is `readonly = 1`,** with `SQL_portalr_tenant` its only `changeable_in_readonly` setting, and fixed limits (10 seconds, 1 GB of memory, 4 threads, 200 million rows or 20 GB read, 100,000 rows answered, 4 queries at once). A read that tries to change any of them, `log_queries` or `readonly` is refused (code 164). The writer's limits (10 seconds, 500 MB, 2 threads, 16 inserts at once) are fixed by constraints (code 452). Both share an hourly quota of 5,000 queries, 500 errors, 500 million rows read and 600 seconds.
- **`langfuse` sees only its own rows** of `system.query_log` and `system.processes`, by a row policy on each.
- **No analytics query reaches `system.query_log`.** Both analytics profiles set `log_queries = 0`, which the reader can't change, being read-only, and the writer can't by a constraint. So `langfuse`, which keeps its grant on that log, sees none of them, failed ones included.
  - Audit of reads is therefore portalr's to keep, not ClickHouse's.
  - The masking rules redact, in any statement that is logged, such as an operator's as `admin`: the value of `SQL_portalr_tenant = '…'`, of `tenant_id = '…'` and `distinct_id = '…'`, and every literal of a `tenant_id IN (…)` or `distinct_id IN (…)` list. Other literals, such as a workspace id, aren't masked.
  - Caveat: the `Settings` column of an operator's own logged query, run with `SQL_portalr_tenant`, still shows the tenant id. Operators run deletions without it.
- **portalr.**
  - `portalr.readers.Analytics` writes as the writer and reads `counts(tenant, span)` as the reader. Each read names the tenant twice, in the setting and in its `WHERE`, each as a parameter, never as text.
  - `actor_of` limits events to people and service principals.
  - `analytics_events.json` is the registry; `member.invited.v1` is its first event, recorded after an invitation succeeds, in a background task, so it never slows or fails the invitation.
  - `config.json`'s `readers` gains `analytics`.
  - Not yet wired into stackr's template (`PORTAL_ANALYTICS_KEY` and ClickHouse's settings in a generated application): the next phase's.
- **Backups.**
  - The single host's backups take `analytics`, made empty where analytics doesn't run.
  - The `backup` user may back it up and make it empty, and owns `restore_analytics`.
  - The drill restores it and checks that it has as many tables as the live one. It checks tables, not rows: rows written since the backup would make a row count differ.
- **The AWS recipe's state host doesn't run analytics yet.** `scripts/check-config` names the two users' settings and files it leaves out.

**The experiment, on ClickHouse 26.9.20.23,** in a throwaway container on 127.0.0.1, and in CI's smoke test:

| Check | Result |
|---|---|
| Reader, setting for tenant A, with and without its own `WHERE` | A's rows only |
| Reader, no setting | Fails: `Unknown setting 'SQL_portalr_tenant'` (code 115) |
| Reader inserts | Refused (497) |
| Reader sets `max_memory_usage`, `max_execution_time`, `max_threads`, `max_rows_to_read`, `max_result_rows`, `log_queries` or `readonly` | Refused (164) |
| Writer sets `max_memory_usage` on an insert | Refused (452) |
| Reader filters on tenant A, with the setting for B | Nothing |
| Users without a row policy (`users_without_row_policies_can_read_rows`, `true` in the image's config) | `admin` reads every tenant, as a future `grafana_analytics` will; the writer has no `SELECT` at all |
| Writer reads | Refused (497) |
| `langfuse` reads `analytics.events` | Refused (497) |
| `langfuse` with an empty password | Refused (516) |
| `system.query_log`, as `langfuse`, after analytics reads, writes and a failed read | Only `langfuse`'s own rows; no analytics query, tenant id or `distinct_id`, in the text, the exception or the settings |
| An operator's statement with a `distinct_id`, a `tenant_id IN (…)` list, a `tenant_id = …` and the tenant setting | Logged as `distinct_id = '***'`, `tenant_id IN ('***')`, `tenant_id = '***'` and `SQL_portalr_tenant = '***'` |

**Cost**, measured on one laptop's Docker (ClickHouse 26.9.20.23; 10 million events over 90 days, 20 tenants, 50,000 people, random 32-hex trace ids):

| Measure | Result |
|---|---|
| Insert, server-side `INSERT SELECT` of 10 million rows | 8.3 s, about 1.2 million rows a second |
| Insert over HTTP as the writer, async inserts waited for: one event | 56 to 75 ms |
| Insert over HTTP as the writer: a batch of 10,000 events | 91 to 106 ms |
| Stored size | 321 MiB compressed for 10 million rows, about 34 bytes a row (1.04 GiB uncompressed); the random trace ids are most of it |
| A three-step `windowFunnel` over 90 days, one tenant (about 500,000 rows), as the reader | 77 to 136 ms |
| Weekly `retention` over four weeks, one tenant | 39 ms |
| Daily active people over 90 days, one tenant | 25 ms |
| ClickHouse's memory with the 10 million rows loaded, analytics alone | 423 MiB |

Langfuse's own load wasn't run beside it here, so its memory with Langfuse on wasn't measured. The smoke row with both profiles is where that shows.

## The relay's slice as built

- **portalr's relay** (`portalr.analytics`), mounted when `portalr_router(relay=…)` is given:
  - `POST /portalr/v1/analytics/session` signs a session id for the signed-in person: a timestamp, a random part, and an HMAC over the person's id under the deployment's key. A batch under a session signed for someone else, or more than 24 hours old, is refused (403).
  - `POST /portalr/v1/events` takes at most 20 events and 16 KB.
    - Each event has at most 10 props, and each value at most 200 characters; more is 413 or 422.
    - The batch must be in a tenant the person is a member of, checked with grantr; the tenant is never the browser's.
    - Without the person's yes, the answer says how many were dropped and nothing is written.
    - Past the person's pace it answers 429 with `Retry-After`.
    - Of each event it keeps only a registry name, the registry's keys and no value with an `@`. A route is kept only if it is one of the app's router's own (`routes.json`, which a test holds to `routeTree.gen.ts`), so a raw path or a query string never is.
    - Browser events have no workspace: the workspace isn't the session's to vouch for.
  - Only a signed-in person may use it: a service principal's key or an agent is refused (403).
  - `GET` and `PUT /portalr/v1/analytics/consent` read and record the person's answer.
    - Only a yes taken back deletes the person's events; a no again, or a no never preceded by a yes, deletes nothing.
    - **Each deletion owed is numbered,** in the consent row (`delete_owed`, and `debts`, how many the person has been owed), by one statement that locks the row (an upsert whose update adds one to `debts`, returning the number): two at once take two numbers, and owing a deletion never writes the answer. A deletion ClickHouse can't take stays owed, and is tried again on the person's next request and by a background pass. The answer's `deleted` says whether it is done.
    - **A yes never cancels a deletion owed.** A no owes the deletion of everything before it; a yes given before it is done leaves it owed, and the next try does it. Its cost: since a deletion is by the person's hash, events they send after that yes and before the deletion is done are deleted too. It is rare, and errs on the side of deleting.
    - **Settling clears only the debt it started with.** A deletion that finishes late, after the person said yes, sent events and said no again, leaves the newer debt owed.
    - **A no that lands while a batch is being written deletes that batch too.** The relay reads the answer again after each write; if it is no longer yes, it owes and tries a new deletion, without touching the answer itself. A yes given meanwhile stays a yes.
    - **The answer is never refused for the person's pace**, so a withdrawal always lands; it is still counted, so a loop of answers drains the pace of the other three routes.
    - **A person's answers set off at most ten deletions an hour.** Past that, the deletion stays owed, and the background pass, which isn't paced, does it: a loop of yes and no costs ClickHouse no more than ten mutations an hour.
  - **Every other relay request is counted first,** per person (20 at once, one a second after), before a database or ClickHouse is asked, so a refused or a dropped request costs a count, not a query. Events have their own, larger, pace.
  - **The body is read no further than 16 KB**: a declared `Content-Length` over it, or a stream that grows past it, is refused (413).
  - **A session id is compared as bytes,** so any text a browser sends is refused (403), never raised on.
  - **Each prop value must be one the registry lists for its key** (an artifact's kind, an integration's key, an outcome). A route must be one of the router's own. Other values are dropped, whatever their spelling, so a lookalike `＠` doesn't get past a check for `@`.
- **Consent** is `portalr_analytics_consent` in the application's database, with `delete_owed` and `debts`, from portalr's first Alembic migration (`portalr_alembic_version`), behind a `Consent` port. Portalr's `sql` extra brings SQLAlchemy and Alembic. On PostgreSQL the application's role is granted reading and writing it, and row-level security keeps each transaction to the person it names (`portalr.user_id`). That holds for the role the application connects as with `DATABASE_ADMIN_URL`; without it, the application's role owns the table and row-level security doesn't hold it. A test on a real PostgreSQL shows one person can't read or write another's row. Replicas starting at once migrate in turn, under an advisory lock.
- **The rate limiter** is `InMemoryRateLimiter`: a token bucket per person, 60 events at once and one a second after, per replica, behind the `RateLimiter` port. It remembers 100,000 people at most, forgetting the one seen longest ago in constant time.
- **stackr's template** wires it all when the four settings are set:
  - `PORTAL_ANALYTICS_URL`;
  - `PORTAL_ANALYTICS_KEY`, which `make env` now generates (`generate:hex`);
  - the two users' passwords.
  - A key that isn't 64 hex digits turns analytics off at start, and says why.
  - The portal migrates the consent table on every start, under an advisory lock, mounts the relay only with a database, since consent must persist, and settles the deletions owed in a background pass about every five minutes (jittered), at most 100 people a pass, read with a `LIMIT`, those who answered longest ago first, so a ClickHouse that is down doesn't hold the start, and a person who never comes back is still deleted. A pass that fails is logged, and the next one tries again; its clients are closed at shutdown whatever it raised. Every replica that starts does so: two may delete the same person's events, which does no harm. A person who says yes and sends events between a replica's reading the deletions owed and its deletion loses those events; it is rare, and errs on the side of deleting.
- **The writer may delete,** `GRANT ALTER DELETE ON analytics.events`, for a person's deletion; the grant reaches every tenant's rows, though the writer still reads none. Langfuse's user now sees only `default`'s rows of `system.mutations`, since a deletion is a mutation that names the person's hash.

**Lightweight deletes, measured on ClickHouse 26.9.20.23** (10 million events over 90 days, 20 tenants, 50,000 people, about 200 events a person):

| Measure | Result |
|---|---|
| A person's deletion, as the writer, over HTTP | 0.18 to 1.04 s; it returns once the rows are masked |
| Rows visible to any read just after, the operator's or a tenant's reader | 0 |
| The mutation | `UPDATE _row_exists = 0 WHERE distinct_id = …`, done at once (`is_done = 1`); it names the person's hash, so only operators may read `system.mutations` for it |
| Rows on disk just after | Still there, masked, until ClickHouse merges the parts that hold them |
| After a merge (`OPTIMIZE … FINAL`, 7.3 s here) | Gone from disk, even with the mask off (`apply_deleted_mask = 0`) |
| With the TTL | The table's TTL still drops old rows; masked rows age out with the rest |
| With backups | A backup taken after the delete holds the rows masked, and they stay masked when restored. A backup taken before it holds them visible until the bucket's lifecycle rule expires it, as P5 says |

So the person sees their events gone at once, and so does an operator's ordinary read. An operator who reads with the mask off, or a backup from before, can still find them until the merge or the backup's expiry.

## The browser's slice as built

- **The OpenAPI document** now has the relay's routes: `portalr.fastapi.openapi` builds the router with a relay. The batch's schema is written in place, so the client's types cover it.
- **The consent switch** is in the account menu, beside colour-blind friendly charts, under "Privacy". It is shown only where `config.json`'s `readers.analytics` is true.
  - It is a checkbox menu item, off until the person turns it on, and turned off with the same one click.
  - Its description is read out with it (`aria-describedby`).
  - There is no banner, no pre-ticked box, and nothing that asks again.
  - It sits beside a link to the privacy guide's "Product analytics", which says what is shared and how it is kept.
  - A status region, there from the start, tells a screen reader the answer as it changes. Where a no's deletion isn't done yet, the menu and the status say so, from the relay's `deleted: false`.
  - The wording, drafted for the owner's review and not final: **"Share how I use the app"**, described as **"Which pages and features you open, never what you write. Off deletes it."**
- **Capture** is an add-on of its own (`ui/src/on-demand/analytics.ts`, 442 bytes gzipped, under a 600-byte ceiling). It is fetched only once the person's answer is yes, so someone who never says yes never loads it.
  - It sends `app.page.viewed.v1` for each page the person opens in a tenant, named by the router's own `fullPath` (`/t/$tenant/w/$workspace/runs`), never the address in the bar.
  - Events wait in memory and go ten at a time, or after five seconds, under a session id portalr signs for the person.
  - A batch the relay doesn't take is dropped, never retried, and never fails a screen.
- **The app's first load** grows by about 1 KB, for the consent read and the switch: 200,751 of its 202,000 bytes, with about 1.2 KB of headroom left. The capture code is outside it.
- **Not yet:** other events than page views (threads, messages, artifacts and integrations are in the registry, for screens to send later), and admin, which sends nothing.

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

Decided by the owner (2026-10-22), with the first slice:

- **The `distinct_id` key is per deployment,** `PORTAL_ANALYTICS_KEY`, which the template's `make env` makes (the relay's slice). One person's events across tenants are deleted with one hash.
- **Umami's data is a schema in the stack's shared PostgreSQL,** not a PostgreSQL of its own: lighter, with its role limited to its schema.
- **Grafana's ClickHouse datasource plugin is baked into the `stackr-grafana` image,** pinned, so Grafana starts offline.

Settled by the first slice: the row-policy-by-setting pattern holds on 26.9.20.23.

Decided by the owner (2026-10-22), for the relay's slice:

- **Consent is a portalr table in the application's PostgreSQL,** portalr's first migration, per person and per deployment, off until a person says yes, and read whether ClickHouse is up or not.
- **Taking back a yes deletes the person's past events at once,** with ClickHouse's lightweight delete by their hashed id.
- **A person's pace is counted per replica, in memory,** behind a `RateLimiter` port, so a limiter over Valkey can take its place without the relay changing. Valkey runs only under the `langfuse` and `gateway` profiles, not under `analytics` alone, so the in-memory limiter is the default.

Settled by the relay's slice: lightweight deletes on 26.9 (below).

Still open:

1. **Browser events carry no workspace**: the workspace isn't the session's to vouch for, and the relay doesn't ask artifactr which workspaces a person may open. A per-workspace adoption view needs that check first.
2. **The writer's `ALTER DELETE` reaches every tenant's rows** (stackr ADR-0044): portalr deletes only by a person's hash, but the grant isn't narrower.
3. Whether grantr needs a removal hook, so a person removed from every tenant has their events deleted too; until then, it is their own no, or an operator's delete.

## Tracking

- [x] Phase 0: this RFC and [stackr ADR-0044](../stackr/adr/0044-clickhouse-a-profile-of-its-own-and-portalrs-analytics-users.md)
- [x] The first slice
- [x] Relay and consent (the server's side)
- [x] Browser capture and the consent UI
- [ ] Grafana's datasource and dashboard
- [ ] Adoption read and page
- [ ] Traces both ways
- [ ] Umami profile, then replay after the privacy review
- [ ] relayr's sink
