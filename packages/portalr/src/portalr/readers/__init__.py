"""portalr's readers: the one module that talks to the stack's tools, for one tenant at a time.

Each reader takes a :class:`~portalr.tenant.Tenant`, which portalr's router makes only after
grantr allows the read, and builds its queries from typed parameters, each naming the tenant.
Each is optional: an application passes those its stack runs.
"""

from dataclasses import dataclass

from portalr.readers.analytics import Adoption, AdoptionQuery, Analytics, EventCount
from portalr.readers.feedback import Feedback, FeedbackQuery, read_feedback
from portalr.readers.grafana import Grafana
from portalr.readers.langfuse import Langfuse, Score, Scores
from portalr.readers.litellm import LiteLLM, Spend, TenantSpend
from portalr.readers.loki import LogQuery, LogRecord, Logs, Loki
from portalr.readers.prometheus import Metric, MetricQuery, Point, Prometheus
from portalr.readers.query import Window
from portalr.readers.reading import Ok, Unavailable, Unconfigured, reading
from portalr.readers.tempo import Span, Tempo, Trace, TraceQuery, TraceSummary
from portalr.readers.umami import UmamiLinks
from portalr.readers.usage import Usage, UsageQuery, read_usage


@dataclass(frozen=True)
class Readers:
    """The tools the application's stack runs; any may be absent."""

    tempo: Tempo | None = None
    loki: Loki | None = None
    prometheus: Prometheus | None = None
    langfuse: Langfuse | None = None
    litellm: LiteLLM | None = None
    grafana: Grafana | None = None
    """Grafana, for operators' deep links into Tempo's and Loki's views."""
    analytics: Analytics | None = None
    """portalr's product analytics on ClickHouse (lattice RFC-0008)."""
    umami: UmamiLinks | None = None
    """Umami, for operators' deep link to its journeys (portalr ADR-0076)."""

    def configured(self) -> dict[str, bool]:
        """Which tools are configured, by name, for the UIs' ``config.json``."""
        return {
            "tempo": self.tempo is not None,
            "loki": self.loki is not None,
            "prometheus": self.prometheus is not None,
            "langfuse": self.langfuse is not None,
            "litellm": self.litellm is not None,
            "grafana": self.grafana is not None,
            "analytics": self.analytics is not None,
            "umami": self.umami is not None,
        }


__all__ = [
    "Adoption",
    "AdoptionQuery",
    "Analytics",
    "EventCount",
    "Feedback",
    "FeedbackQuery",
    "Grafana",
    "Langfuse",
    "LiteLLM",
    "LogQuery",
    "LogRecord",
    "Logs",
    "Loki",
    "Metric",
    "MetricQuery",
    "Ok",
    "Point",
    "Prometheus",
    "Readers",
    "Score",
    "Scores",
    "Span",
    "Spend",
    "Tempo",
    "TenantSpend",
    "Trace",
    "TraceQuery",
    "TraceSummary",
    "UmamiLinks",
    "Unavailable",
    "Unconfigured",
    "Usage",
    "UsageQuery",
    "Window",
    "read_feedback",
    "read_usage",
    "reading",
]
