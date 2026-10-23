"""Every query a reader can send names the tenant: the filters are tested where they are built."""

import json
import re
from datetime import UTC, datetime, timedelta
from itertools import product

import pytest
from pydantic import ValidationError

from portalr.readers import LogQuery, MetricQuery, TraceQuery, Window
from portalr.readers.langfuse import tenant_tag, trace_parameters
from portalr.readers.litellm import team
from portalr.readers.loki import logs_query
from portalr.readers.prometheus import QUERIES, TENANT_LABEL
from portalr.readers.prometheus import parameters as prometheus_parameters
from portalr.readers.tempo import search_query
from portalr.tenant import allowed

ACME = allowed("acme")
START = datetime(2026, 10, 12, tzinfo=UTC)
END = START + timedelta(hours=1)
IDS = (None, "thr_1", "run.2:x")


def test_every_trace_search_names_the_tenant_first() -> None:
    for session, run in product(IDS, IDS):
        query = search_query(ACME, TraceQuery(start=START, end=END, session=session, run=run))
        assert query.startswith('{ span.tenant.id = "acme"'), query
        if session:
            assert f'span.session.id = "{session}"' in query
        if run:
            assert f'(span.artifactr.run.id = "{run}" || span.reflexr.run.id = "{run}")' in query


SESSION = "1792800000-0123456789abcdef"


def test_an_analytics_sessions_search_names_the_tenant_and_the_session_each_quoted() -> None:
    for session, run in product(IDS, IDS):
        query = search_query(
            ACME,
            TraceQuery(start=START, end=END, session=session, run=run, analytics_session=SESSION),
        )
        # The tenant's spans and the session's server span, in the same trace.
        assert query.startswith('{ span.tenant.id = "acme"'), query
        assert query.endswith(f' && {{ span.portalr.analytics.session = "{SESSION}" }}'), query
    quoted = search_query(
        allowed('a"b'), TraceQuery(start=START, end=END, analytics_session=SESSION)
    )
    assert quoted.startswith('{ span.tenant.id = "a\\"b" }'), quoted


@pytest.mark.parametrize(
    "session",
    [
        "",
        "thr_1",
        "1792800000-0123456789ABCDEF",
        '1-0123456789abcdef" } || { true',
        "1-" + "a" * 17,
    ],
)
def test_an_analytics_session_is_only_one_the_relay_could_have_made(session: str) -> None:
    with pytest.raises(ValidationError):
        TraceQuery(start=START, end=END, analytics_session=session)


def test_an_analytics_sessions_window_is_at_most_91_days() -> None:
    TraceQuery(start=START, end=START + timedelta(days=91), analytics_session=SESSION)
    with pytest.raises(ValidationError, match="at most 91 days"):
        TraceQuery(start=START, end=START + timedelta(days=92), analytics_session=SESSION)
    # Without one, a search's window is as before.
    TraceQuery(start=START, end=START + timedelta(days=92))


def test_every_log_query_filters_on_the_tenant_first() -> None:
    for thread, run in product(IDS, IDS):
        query = logs_query(ACME, LogQuery(start=START, end=END, thread=thread, run=run))
        assert query.startswith('{service_name=~".+"} | tenant_id = "acme"'), query
        if thread:
            assert f'| artifactr_thread_id = "{thread}"' in query
        if run:
            assert f'| artifactr_run_id = "{run}" or reflexr_run_id = "{run}"' in query


def test_every_metric_goes_through_the_proxy_with_the_tenant() -> None:
    for metric in QUERIES:
        query = MetricQuery(start=START, end=END, metric=metric)
        sent = prometheus_parameters(ACME, query)
        assert sent[TENANT_LABEL] == "acme"
        selectors = re.findall(r"\{[^{}]*\}", str(sent["query"]))
        assert selectors, metric
        assert all('tenant_id="acme"' in selector for selector in selectors), sent["query"]
        assert sent["step"] == 300


def test_every_score_read_filters_on_the_tenants_tag() -> None:
    assert tenant_tag(ACME) == "tenant:acme"
    sent = trace_parameters(ACME, Window(start=START, end=END, limit=10), workspace="notes")
    conditions = json.loads(str(sent["filter"]))
    assert {
        "type": "arrayOptions",
        "column": "traceTags",
        "operator": "all of",
        "value": ["tenant:acme", "workspace:notes"],
    } in conditions
    # Each read pages its own: no limit in the conditions.
    assert "limit" not in sent


def test_spend_is_read_from_the_tenants_team() -> None:
    assert team(ACME) == "tenant-acme"


@pytest.mark.parametrize("bad", ['thr" || span.tenant.id = "globex', "a b", "", "x" * 129])
def test_an_id_that_could_change_a_query_is_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        TraceQuery(start=START, end=END, session=bad)
    with pytest.raises(ValidationError):
        LogQuery(start=START, end=END, run=bad)
