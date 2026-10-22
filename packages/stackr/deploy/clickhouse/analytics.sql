-- portalr's analytics database (lattice RFC-0008, stackr ADR-0044), made as ClickHouse's admin by
-- clickhouse-init, every time the analytics profile starts, with @RETENTION@ the deployment's
-- ANALYTICS_RETENTION_DAYS. Each statement is safe to run again.
CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.events
(
    ts DateTime64(3, 'UTC'),
    tenant_id LowCardinality(String),
    workspace_id String,
    distinct_id FixedString(32),
    event LowCardinality(String),
    trace_id String,
    session_id String,
    actor_kind LowCardinality(String),
    props Map(LowCardinality(String), String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (tenant_id, workspace_id, event, ts)
TTL toDateTime(ts) + INTERVAL @RETENTION@ DAY;

-- The retention the deployment chose, set again on each start.
ALTER TABLE analytics.events MODIFY TTL toDateTime(ts) + INTERVAL @RETENTION@ DAY;
