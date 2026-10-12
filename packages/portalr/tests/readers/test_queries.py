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
    sent = trace_parameters(ACME, Window(start=START, end=END, limit=10))
    conditions = json.loads(str(sent["filter"]))
    assert {
        "type": "arrayOptions",
        "column": "traceTags",
        "operator": "all of",
        "value": ["tenant:acme"],
    } in conditions
    assert sent["limit"] == 10


def test_spend_is_read_from_the_tenants_team() -> None:
    assert team(ACME) == "tenant-acme"


@pytest.mark.parametrize("bad", ['thr" || span.tenant.id = "globex', "a b", "", "x" * 129])
def test_an_id_that_could_change_a_query_is_refused(bad: str) -> None:
    with pytest.raises(ValidationError):
        TraceQuery(start=START, end=END, session=bad)
    with pytest.raises(ValidationError):
        LogQuery(start=START, end=END, run=bad)
