"""artifactr's Grafana dashboards, generated into deploy/grafana/dashboards/.

Run ``make dashboards`` after changing them. The dashboards read Prometheus (data source uid
``prometheus``, as stackr provisions it) with the names the OTLP translation gives artifactr's
metrics; ``tests/test_dashboards.py`` checks every query against the metric registry, and that
the checked-in files match this script.
"""

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

OUT = Path(__file__).parent.parent / "deploy" / "grafana" / "dashboards"
PROMETHEUS = {"type": "prometheus", "uid": "prometheus"}
RATE = "$__rate_interval"

# Selectors for the template variables each dashboard offers.
JOB = 'job=~"$job"'
TENANT = f'{JOB}, artifactr_tenant_id=~"$tenant"'
WORKSPACE = f'{TENANT}, artifactr_workspace_id=~"$workspace"'


def rate(metric: str, selector: str, *, by: str = "", extra: str = "") -> str:
    """``sum by (...) (rate(metric{selector}[...]))``."""
    matchers = ", ".join(part for part in (selector, extra) if part)
    grouping = f" by ({by})" if by else ""
    return f"sum{grouping} (rate({metric}{{{matchers}}}[{RATE}]))"


def quantile(q: float, histogram: str, selector: str, *, by: str = "") -> str:
    """A quantile of a histogram over the rate interval, optionally per label."""
    labels = f"le, {by}" if by else "le"
    return f"histogram_quantile({q}, {rate(f'{histogram}_bucket', selector, by=labels)})"


def ratio(numerator: str, denominator: str) -> str:
    """One rate over another, zero when there is nothing to divide by."""
    return f"({numerator}) / clamp_min({denominator}, 1e-9)"


class Layout:
    """Places panels on Grafana's 24-column grid, row by row."""

    def __init__(self) -> None:
        self.panels: list[dict[str, Any]] = []
        self._y = 0
        self._x = 0
        self._height = 0

    def row(self, title: str) -> None:
        """Start a row: a full-width title above the panels that follow."""
        self._newline()
        self.panels.append(
            {
                "type": "row",
                "title": title,
                "collapsed": False,
                "gridPos": {"x": 0, "y": self._y, "w": 24, "h": 1},
                "panels": [],
            }
        )
        self._y += 1

    def add(self, panel: dict[str, Any], *, width: int, height: int) -> None:
        """Place a panel after the previous one, wrapping to a new line when it is full."""
        if self._x + width > 24:
            self._newline()
        panel["gridPos"] = {"x": self._x, "y": self._y, "w": width, "h": height}
        self.panels.append(panel)
        self._x += width
        self._height = max(self._height, height)

    def _newline(self) -> None:
        self._y += self._height
        self._x = 0
        self._height = 0


def stat(layout: Layout, title: str, expr: str, *, unit: str, description: str) -> None:
    """Add a single-number panel."""
    layout.add(
        {
            "type": "stat",
            "title": title,
            "description": description,
            "datasource": PROMETHEUS,
            "targets": [{"refId": "A", "expr": expr, "datasource": PROMETHEUS}],
            "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "colorMode": "none",
                "graphMode": "area",
            },
        },
        width=6,
        height=4,
    )


def series(
    layout: Layout,
    title: str,
    targets: list[tuple[str, str]],
    *,
    unit: str,
    description: str,
    width: int = 12,
    exemplars: bool = False,
) -> None:
    """Add a time series panel, one line per target."""
    layout.add(
        {
            "type": "timeseries",
            "title": title,
            "description": description,
            "datasource": PROMETHEUS,
            "targets": [
                {
                    "refId": chr(ord("A") + index),
                    "expr": expr,
                    "legendFormat": legend,
                    "exemplar": exemplars,
                    "datasource": PROMETHEUS,
                }
                for index, (expr, legend) in enumerate(targets)
            ],
            "fieldConfig": {
                "defaults": {"unit": unit, "custom": {"fillOpacity": 10, "lineWidth": 1}},
                "overrides": [],
            },
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
        },
        width=width,
        height=8,
    )


def variable(name: str, label: str, query: str) -> dict[str, Any]:
    """A template variable whose values come from a label."""
    return {
        "name": name,
        "label": label,
        "type": "query",
        "datasource": PROMETHEUS,
        "query": {"query": query, "refId": name},
        "definition": query,
        "refresh": 2,
        "includeAll": True,
        "multi": True,
        "allValue": ".*",
        "sort": 1,
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
    }


def variables(scope: str) -> list[dict[str, Any]]:
    """The template variables down to ``scope``: job, then tenant, then workspace."""
    found = [variable("job", "Service", "label_values(artifactr_commands_total, job)")]
    if scope in ("tenant", "workspace"):
        query = f"label_values(artifactr_commands_total{{{JOB}}}, artifactr_tenant_id)"
        found.append(variable("tenant", "Tenant", query))
    if scope == "workspace":
        query = f"label_values(artifactr_commands_total{{{TENANT}}}, artifactr_workspace_id)"
        found.append(variable("workspace", "Workspace", query))
    return found


def dashboard(uid: str, title: str, description: str, scope: str, layout: Layout) -> dict[str, Any]:
    """A dashboard around a layout's panels, with the variables down to ``scope``."""
    return {
        "uid": f"artifactr-{uid}",
        "title": f"artifactr / {title}",
        "description": description,
        "tags": ["artifactr"],
        "timezone": "browser",
        "editable": True,
        "graphTooltip": 1,
        "schemaVersion": 39,
        "version": 1,
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "links": [
            {
                "title": "artifactr dashboards",
                "type": "dashboards",
                "tags": ["artifactr"],
                "asDropdown": True,
                "includeVars": True,
                "keepTime": True,
            }
        ],
        "templating": {"list": variables(scope)},
        "annotations": {"list": []},
        "panels": layout.panels,
    }


# ─── the dashboards ───────────────────────────────────────────────────────────


def overview() -> dict[str, Any]:
    """Every tenant at a glance."""
    layout = Layout()
    stat(
        layout,
        "Commands",
        rate("artifactr_commands_total", JOB),
        unit="reqps",
        description="Commands committed per second, every tenant.",
    )
    stat(
        layout,
        "Rejected or failed",
        ratio(
            rate("artifactr_commands_total", JOB, extra='artifactr_outcome=~"rejected|error"'),
            rate("artifactr_commands_total", JOB),
        ),
        unit="percentunit",
        description="The share of commands rejected by the rules or failed on the server.",
    )
    stat(
        layout,
        "Turns",
        rate("artifactr_turns_total", JOB),
        unit="reqps",
        description="Turns started or resumed per second.",
    )
    stat(
        layout,
        "Open connections",
        f"sum(artifactr_stream_connections{{{JOB}}})",
        unit="short",
        description="Thread-protocol WebSocket connections open now.",
    )
    layout.row("Activity")
    series(
        layout,
        "Commands by tenant",
        [
            (
                f"topk(10, {rate('artifactr_commands_total', JOB, by='artifactr_tenant_id')})",
                "{{artifactr_tenant_id}}",
            )
        ],
        unit="reqps",
        description="The ten busiest tenants.",
    )
    series(
        layout,
        "Turns by outcome",
        [
            (
                rate("artifactr_turns_total", JOB, by="artifactr_turn_outcome"),
                "{{artifactr_turn_outcome}}",
            )
        ],
        unit="reqps",
        description="Completed, paused (waiting on people), stopped and failed turns.",
    )
    series(
        layout,
        "Turn duration",
        [
            (quantile(0.5, "artifactr_turn_duration_seconds", JOB), "p50"),
            (quantile(0.95, "artifactr_turn_duration_seconds", JOB), "p95"),
        ],
        unit="s",
        description="From a turn's start to its end or pause. Exemplars link to the turn's trace.",
        exemplars=True,
    )
    series(
        layout,
        "Tokens by tenant",
        [
            (
                f"topk(10, {rate('artifactr_tokens_total', JOB, by='artifactr_tenant_id')})",
                "{{artifactr_tenant_id}}",
            )
        ],
        unit="short",
        description="Model tokens per second, from runs' recorded usage.",
    )
    return dashboard(
        "overview",
        "Overview",
        "Every tenant: commands, turns, latency and tokens.",
        "job",
        layout,
    )


def tenant() -> dict[str, Any]:
    """One tenant's workspaces and usage."""
    layout = Layout()
    stat(
        layout,
        "Commands",
        rate("artifactr_commands_total", TENANT),
        unit="reqps",
        description="Commands committed per second.",
    )
    stat(
        layout,
        "Turns",
        rate("artifactr_turns_total", TENANT),
        unit="reqps",
        description="Turns started or resumed per second.",
    )
    stat(
        layout,
        "Tokens",
        rate("artifactr_tokens_total", TENANT),
        unit="short",
        description="Model tokens per second.",
    )
    stat(
        layout,
        "Feedback",
        rate("artifactr_feedback_total", TENANT),
        unit="reqps",
        description="Feedback given per second, by people and evaluators.",
    )
    layout.row("Workspaces")
    series(
        layout,
        "Commands by workspace",
        [
            (
                "topk(10, "
                + rate("artifactr_commands_total", TENANT, by="artifactr_workspace_id")
                + ")",
                "{{artifactr_workspace_id}}",
            )
        ],
        unit="reqps",
        description="The ten busiest workspaces.",
    )
    series(
        layout,
        "Tokens by workspace",
        [
            (
                f"topk(10, {rate('artifactr_tokens_total', TENANT, by='artifactr_workspace_id')})",
                "{{artifactr_workspace_id}}",
            )
        ],
        unit="short",
        description="The workspaces using the most model tokens.",
    )
    series(
        layout,
        "Messages by kind of actor",
        [
            (
                rate("artifactr_messages_total", TENANT, by="artifactr_actor_kind"),
                "{{artifactr_actor_kind}}",
            )
        ],
        unit="reqps",
        description="Messages from people, the agent and external agents.",
    )
    series(
        layout,
        "Turn duration",
        [(quantile(0.95, "artifactr_turn_duration_seconds", TENANT), "p95")],
        unit="s",
        description="The 95th percentile of turn duration.",
        exemplars=True,
    )
    return dashboard(
        "tenant", "Tenant", "One tenant's workspaces, usage and activity.", "tenant", layout
    )


def workspace() -> dict[str, Any]:
    """One workspace's activity."""
    layout = Layout()
    series(
        layout,
        "Commands by type",
        [
            (
                rate("artifactr_commands_total", WORKSPACE, by="artifactr_command_type"),
                "{{artifactr_command_type}}",
            )
        ],
        unit="reqps",
        description="Commands committed per second, by type.",
    )
    series(
        layout,
        "Rejections",
        [
            (
                rate(
                    "artifactr_commands_total",
                    WORKSPACE,
                    by="artifactr_rejection",
                    extra='artifactr_outcome="rejected"',
                ),
                "{{artifactr_rejection}}",
            )
        ],
        unit="reqps",
        description="Commands the rules rejected, by reason, such as version conflicts.",
    )
    series(
        layout,
        "Artifact changes",
        [
            (
                rate(
                    "artifactr_artifact_changes_total",
                    WORKSPACE,
                    by="artifactr_artifact_kind, artifactr_actor_kind",
                ),
                "{{artifactr_artifact_kind}} by {{artifactr_actor_kind}}",
            )
        ],
        unit="reqps",
        description="Artifacts created, changed and archived, by kind and by who.",
    )
    series(
        layout,
        "Turns by outcome",
        [
            (
                rate("artifactr_turns_total", WORKSPACE, by="artifactr_turn_outcome"),
                "{{artifactr_turn_outcome}}",
            )
        ],
        unit="reqps",
        description="Completed, paused, stopped and failed turns.",
    )
    series(
        layout,
        "Tool calls",
        [
            (
                rate(
                    "artifactr_tool_calls_total",
                    WORKSPACE,
                    by="gen_ai_tool_name, artifactr_tool_status",
                ),
                "{{gen_ai_tool_name}} {{artifactr_tool_status}}",
            )
        ],
        unit="reqps",
        description="The agent's tool calls, by tool and how they ended.",
    )
    series(
        layout,
        "Feedback",
        [
            (
                rate(
                    "artifactr_feedback_total",
                    WORKSPACE,
                    by="artifactr_feedback_type, artifactr_actor_kind",
                ),
                "{{artifactr_feedback_type}} by {{artifactr_actor_kind}}",
            )
        ],
        unit="reqps",
        description="Feedback given, by type and by people or evaluators.",
    )
    return dashboard(
        "workspace",
        "Workspace",
        "One workspace: commands, changes, turns, tools and feedback.",
        "workspace",
        layout,
    )


def agent() -> dict[str, Any]:
    """Models, runs and tools."""
    layout = Layout()
    layout.row("Models")
    series(
        layout,
        "Tokens by model",
        [
            (
                rate(
                    "gen_ai_client_token_usage_sum",
                    JOB,
                    by="gen_ai_request_model, gen_ai_token_type",
                ),
                "{{gen_ai_request_model}} {{gen_ai_token_type}}",
            )
        ],
        unit="short",
        description="Tokens per second, from pydantic-ai's gen_ai.client.token.usage.",
    )
    series(
        layout,
        "Cost by model",
        [(rate("operation_cost_sum", JOB, by="gen_ai_request_model"), "{{gen_ai_request_model}}")],
        unit="currencyUSD",
        description="Estimated spend per second, from pydantic-ai's operation.cost.",
    )
    series(
        layout,
        "Time to first chunk",
        [
            (
                quantile(
                    0.95,
                    "gen_ai_client_operation_time_to_first_chunk_seconds",
                    JOB,
                    by="gen_ai_request_model",
                ),
                "{{gen_ai_request_model}} p95",
            )
        ],
        unit="s",
        description="How long streamed model responses take to start.",
    )
    series(
        layout,
        "Tokens by tenant",
        [
            (
                rate("artifactr_tokens_total", TENANT, by="artifactr_tenant_id, gen_ai_token_type"),
                "{{artifactr_tenant_id}} {{gen_ai_token_type}}",
            )
        ],
        unit="short",
        description="Tokens per second by tenant, from runs' recorded usage.",
    )
    layout.row("Runs and tools")
    series(
        layout,
        "Run segments by status",
        [
            (
                rate("artifactr_runs_total", TENANT, by="artifactr_run_status"),
                "{{artifactr_run_status}}",
            )
        ],
        unit="reqps",
        description="Run segments that completed, paused, were stopped or failed.",
    )
    series(
        layout,
        "Turn duration",
        [
            (quantile(0.5, "artifactr_turn_duration_seconds", TENANT), "p50"),
            (quantile(0.95, "artifactr_turn_duration_seconds", TENANT), "p95"),
        ],
        unit="s",
        description="Exemplars link to the turn's trace.",
        exemplars=True,
    )
    series(
        layout,
        "Tool failure rate",
        [
            (
                ratio(
                    rate(
                        "artifactr_tool_calls_total",
                        TENANT,
                        by="gen_ai_tool_name",
                        extra='artifactr_tool_status="error"',
                    ),
                    rate("artifactr_tool_calls_total", TENANT, by="gen_ai_tool_name"),
                ),
                "{{gen_ai_tool_name}}",
            )
        ],
        unit="percentunit",
        description="The share of each tool's calls that ended in an error.",
    )
    series(
        layout,
        "Tool retries",
        [
            (
                rate(
                    "artifactr_tool_calls_total",
                    TENANT,
                    by="gen_ai_tool_name",
                    extra='artifactr_tool_status="retry"',
                ),
                "{{gen_ai_tool_name}}",
            )
        ],
        unit="reqps",
        description="Calls answered with a retry: a rejection, or the tool's own ModelRetry.",
    )
    return dashboard(
        "agent",
        "Agent and LLM",
        "Model usage, cost and latency; run outcomes; tool failures.",
        "tenant",
        layout,
    )


def collaboration() -> dict[str, Any]:
    """Proposals, edits and feedback."""
    layout = Layout()
    series(
        layout,
        "Proposals",
        [
            (
                rate("artifactr_proposals_total", TENANT, by="artifactr_proposal_action"),
                "{{artifactr_proposal_action}}",
            )
        ],
        unit="reqps",
        description="Proposals created, accepted and rejected.",
    )
    series(
        layout,
        "Acceptance rate",
        [
            (
                ratio(
                    rate(
                        "artifactr_proposals_total",
                        TENANT,
                        extra='artifactr_proposal_action="accepted"',
                    ),
                    rate(
                        "artifactr_proposals_total",
                        TENANT,
                        extra='artifactr_proposal_action=~"accepted|rejected"',
                    ),
                ),
                "accepted",
            )
        ],
        unit="percentunit",
        description="The share of decided proposals that were accepted.",
    )
    series(
        layout,
        "Changes by who",
        [
            (
                rate(
                    "artifactr_artifact_changes_total",
                    TENANT,
                    by="artifactr_actor_kind",
                    extra='artifactr_change="changed"',
                ),
                "{{artifactr_actor_kind}}",
            )
        ],
        unit="reqps",
        description="Artifact edits by people, the agent and external agents.",
    )
    series(
        layout,
        "Agent's share of edits",
        [
            (
                ratio(
                    rate(
                        "artifactr_artifact_changes_total",
                        TENANT,
                        extra='artifactr_change="changed", artifactr_actor_kind="agent"',
                    ),
                    rate(
                        "artifactr_artifact_changes_total",
                        TENANT,
                        extra='artifactr_change="changed"',
                    ),
                ),
                "agent",
            )
        ],
        unit="percentunit",
        description="The share of artifact edits made by the agent.",
    )
    series(
        layout,
        "Feedback by type",
        [
            (
                rate(
                    "artifactr_feedback_total",
                    TENANT,
                    by="artifactr_feedback_type, artifactr_feedback_target",
                ),
                "{{artifactr_feedback_type}} on {{artifactr_feedback_target}}",
            )
        ],
        unit="reqps",
        description="Feedback given, by type and what it is about.",
    )
    series(
        layout,
        "Feedback by who",
        [
            (
                rate("artifactr_feedback_total", TENANT, by="artifactr_actor_kind"),
                "{{artifactr_actor_kind}}",
            )
        ],
        unit="reqps",
        description="Feedback from people and from evaluators.",
    )
    return dashboard(
        "collaboration",
        "Collaboration",
        "How people and agents share the work: proposals, edits and feedback.",
        "tenant",
        layout,
    )


def surfaces() -> dict[str, Any]:
    """REST, WebSocket and MCP."""
    http = f'{JOB}, http_route=~"/v1/.*"'
    mcp = f'{JOB}, http_route=~"/mcp.*"'
    layout = Layout()
    layout.row("REST and MCP")
    series(
        layout,
        "REST requests",
        [
            (
                rate(
                    "http_server_request_duration_seconds_count",
                    http,
                    by="http_route, http_response_status_code",
                ),
                "{{http_route}} {{http_response_status_code}}",
            )
        ],
        unit="reqps",
        description="Requests to artifactr's router, by route and status.",
    )
    series(
        layout,
        "REST latency",
        [
            (
                quantile(0.95, "http_server_request_duration_seconds", http, by="http_route"),
                "{{http_route}} p95",
            )
        ],
        unit="s",
        description="The 95th percentile of request duration, by route.",
        exemplars=True,
    )
    series(
        layout,
        "MCP requests",
        [
            (
                rate(
                    "http_server_request_duration_seconds_count",
                    mcp,
                    by="http_response_status_code",
                ),
                "{{http_response_status_code}}",
            )
        ],
        unit="reqps",
        description="Requests to the MCP server, when it is mounted at /mcp.",
    )
    series(
        layout,
        "Requests in progress",
        [(f"sum(http_server_active_requests{{{JOB}}})", "requests")],
        unit="short",
        description="HTTP requests being served now.",
    )
    layout.row("WebSocket")
    series(
        layout,
        "Open connections",
        [
            (
                f"sum by (artifactr_tenant_id) (artifactr_stream_connections{{{JOB}}})",
                "{{artifactr_tenant_id}}",
            )
        ],
        unit="short",
        description="Thread-protocol connections open now, by tenant.",
    )
    series(
        layout,
        "Disconnects by close code",
        [
            (
                rate("artifactr_stream_disconnects_total", JOB, by="artifactr_stream_close_code"),
                "{{artifactr_stream_close_code}}",
            )
        ],
        unit="reqps",
        description="1000 is normal; 4401 and 4403 refusals; 4429 a client too slow to keep up.",
    )
    layout.row("Commands by surface")
    series(
        layout,
        "Commands by kind of actor",
        [
            (
                rate("artifactr_commands_total", JOB, by="artifactr_actor_kind"),
                "{{artifactr_actor_kind}}",
            )
        ],
        unit="reqps",
        description="People over REST and WebSocket, external agents over MCP, the agent.",
        width=24,
    )
    return dashboard(
        "surfaces",
        "Surfaces",
        "REST, WebSocket and MCP: traffic, latency and connections.",
        "job",
        layout,
    )


def storage() -> dict[str, Any]:
    """Commits and the database."""
    layout = Layout()
    series(
        layout,
        "Commit latency",
        [
            (quantile(0.5, "artifactr_commit_duration_seconds", JOB), "p50"),
            (quantile(0.95, "artifactr_commit_duration_seconds", JOB), "p95"),
            (quantile(0.99, "artifactr_commit_duration_seconds", JOB), "p99"),
        ],
        unit="s",
        description="Committing a command, storage included. Exemplars link to the commit's trace.",
        exemplars=True,
    )
    series(
        layout,
        "Commit latency by command",
        [
            (
                quantile(
                    0.95, "artifactr_commit_duration_seconds", JOB, by="artifactr_command_type"
                ),
                "{{artifactr_command_type}} p95",
            )
        ],
        unit="s",
        description="The 95th percentile, by command type.",
    )
    series(
        layout,
        "Version conflicts",
        [
            (
                rate(
                    "artifactr_commands_total",
                    JOB,
                    by="artifactr_tenant_id",
                    extra='artifactr_rejection="version_conflict"',
                ),
                "{{artifactr_tenant_id}}",
            )
        ],
        unit="reqps",
        description="Edits based on an outdated version: contention on shared artifacts.",
    )
    series(
        layout,
        "Database connections",
        [(f"sum by (state) (db_client_connections_usage{{{JOB}}})", "{{state}}")],
        unit="short",
        description="SQLAlchemy's pool: connections in use and idle.",
    )
    series(
        layout,
        "Commands failed on the server",
        [
            (
                rate(
                    "artifactr_commands_total",
                    JOB,
                    by="artifactr_command_type",
                    extra='artifactr_outcome="error"',
                ),
                "{{artifactr_command_type}}",
            )
        ],
        unit="reqps",
        description="Commits that raised an unexpected error, such as a storage failure.",
        width=24,
    )
    return dashboard(
        "storage",
        "Storage",
        "Commit latency, contention and the database pool.",
        "job",
        layout,
    )


DASHBOARDS = {
    "overview": overview,
    "tenant": tenant,
    "workspace": workspace,
    "agent": agent,
    "collaboration": collaboration,
    "surfaces": surfaces,
    "storage": storage,
}


def rendered() -> Iterator[tuple[str, str]]:
    """Every dashboard's file name and JSON text."""
    for name, build in DASHBOARDS.items():
        yield f"artifactr-{name}.json", json.dumps(build(), indent=2) + "\n"


def main() -> None:
    """Write every dashboard."""
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in rendered():
        (OUT / name).write_text(text)
    sys.stdout.write(f"wrote {len(DASHBOARDS)} dashboards to {OUT}\n")


if __name__ == "__main__":
    main()
