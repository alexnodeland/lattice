"""The Grafana dashboards cannot drift from the metric registry, or from their generator."""

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from artifactr.telemetry import EXTERNAL_METRICS, METRICS, Metric

ROOT = Path(__file__).parent.parent
DASHBOARDS = ROOT / "deploy" / "grafana" / "dashboards"

RESOURCE_LABELS = {"job", "instance", "le", "deployment_environment_name", "service_version"}
"""Labels every series has: from the resource (stackr's Prometheus promotes the last two)."""

KEYWORDS = {"by", "without", "on", "ignoring", "group_left", "group_right", "bool", "and", "or"}
KEYWORDS |= {"unless", "offset", "inf", "nan"}

SERIES: dict[str, Metric] = {
    series: metric
    for metric in (*METRICS.values(), *EXTERNAL_METRICS.values())
    for series in metric.prometheus_series
}
"""Every Prometheus series name a dashboard may use, and the metric it belongs to."""


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "grafana_dashboards", ROOT / "scripts" / "grafana_dashboards.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dashboards() -> dict[str, dict[str, Any]]:
    return {path.name: json.loads(path.read_text()) for path in sorted(DASHBOARDS.glob("*.json"))}


def _panels(panels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for panel in panels:
        found.append(panel)
        found.extend(_panels(panel.get("panels", [])))
    return found


def _queries(dashboard: dict[str, Any]) -> list[str]:
    queries = [
        target["expr"]
        for panel in _panels(dashboard["panels"])
        for target in panel.get("targets", [])
    ]
    for variable in dashboard["templating"]["list"]:
        selector, _ = _label_values(variable["query"]["query"])
        queries.append(selector)
    return queries


def _label_values(query: str) -> tuple[str, str]:
    match = re.fullmatch(r"label_values\((.*),\s*([a-zA-Z_][a-zA-Z0-9_]*)\)", query)
    assert match, f"not a label_values query: {query}"
    return match.group(1), match.group(2)


def metric_names(expr: str) -> set[str]:
    """The series a PromQL expression reads."""
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', expr)
    text = re.sub(r"\{[^}]*\}", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\b(by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)", "", text)
    names: set[str] = set()
    for match in re.finditer(r"[a-zA-Z_:][a-zA-Z0-9_:]*", text):
        before = text[match.start() - 1] if match.start() else " "
        after = text[match.end() :].lstrip()
        if before.isdigit() or before == "." or after.startswith("("):
            continue  # a number's exponent, or a function
        if match.group() not in KEYWORDS:
            names.add(match.group())
    return names


def label_names(expr: str) -> set[str]:
    """The labels a PromQL expression matches on or groups by."""
    labels: set[str] = set()
    for matchers in re.findall(r"\{([^}]*)\}", expr):
        labels |= set(re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=~|!~|!=|=)", matchers))
    for grouping in re.findall(r"\b(?:by|without)\s*\(([^)]*)\)", expr):
        labels |= {label.strip() for label in grouping.split(",") if label.strip()}
    return labels


def _prometheus(attribute: str) -> str:
    return attribute.replace(".", "_")


def test_there_is_a_dashboard_for_each_view() -> None:
    assert set(_dashboards()) == {
        "artifactr-overview.json",
        "artifactr-tenant.json",
        "artifactr-workspace.json",
        "artifactr-agent.json",
        "artifactr-collaboration.json",
        "artifactr-surfaces.json",
        "artifactr-storage.json",
    }


def problems(query: str) -> list[str]:
    """What is wrong with a query: metrics outside the registry, or labels a metric lacks.

    Labels are checked for artifactr's own metrics, whose attributes the registry declares.
    """
    names = metric_names(query)
    if not names:
        return [f"no metric in {query}"]
    unknown = names - set(SERIES)
    if unknown:
        return [f"{sorted(unknown)} in {query} are not in the registry"]
    metrics = {SERIES[series] for series in names}
    if any(metric.name not in METRICS for metric in metrics):
        return []
    allowed = RESOURCE_LABELS | {
        _prometheus(attribute) for metric in metrics for attribute in metric.attributes
    }
    extra = label_names(query) - allowed
    return [f"{sorted(extra)} are not attributes of {query}"] if extra else []


@pytest.mark.parametrize("name", sorted(_dashboards()))
def test_every_query_reads_a_metric_in_the_registry(name: str) -> None:
    for query in _queries(_dashboards()[name]):
        assert problems(query) == [], name


def test_drift_is_caught() -> None:
    assert problems("sum(rate(artifactr_commands_total[5m]))") == []
    assert problems("sum(rate(artifactr_commits_total[5m]))") == [
        "['artifactr_commits_total'] in sum(rate(artifactr_commits_total[5m])) are not in "
        "the registry"
    ]
    by_thread = "sum by (artifactr_thread_id) (rate(artifactr_commands_total[5m]))"
    assert problems(by_thread) == [f"['artifactr_thread_id'] are not attributes of {by_thread}"]
    assert problems('sum by (gen_ai_request_model) (rate(operation_cost_sum{x="y"}[5m]))') == []
    assert problems("vector(1)") == ["no metric in vector(1)"]


@pytest.mark.parametrize("name", sorted(_dashboards()))
def test_dashboards_read_stackrs_prometheus(name: str) -> None:
    dashboard = _dashboards()[name]
    assert dashboard["uid"] == name.removesuffix(".json")
    assert "artifactr" in dashboard["tags"]
    for panel in _panels(dashboard["panels"]):
        if panel["type"] != "row":
            assert panel["datasource"] == {"type": "prometheus", "uid": "prometheus"}
            assert panel["description"], f"{name}: {panel['title']} has no description"


def test_the_checked_in_dashboards_are_generated() -> None:
    generated = dict(_generator().rendered())
    assert generated == {path.name: path.read_text() for path in DASHBOARDS.glob("*.json")}, (
        "run `make dashboards`"
    )


def test_the_query_parser() -> None:
    expr = (
        "histogram_quantile(0.95, sum by (le, x) "
        '(rate(a_bucket{j=~"$j", y="1"}[$__rate_interval])))'
        " / clamp_min(b_total offset 5m, 1e-9)"
    )
    assert metric_names(expr) == {"a_bucket", "b_total"}
    assert label_names(expr) == {"le", "x", "j", "y"}
    assert _label_values('label_values(m{job=~"$job"}, t)') == ('m{job=~"$job"}', "t")
