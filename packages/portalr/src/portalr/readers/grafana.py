"""Grafana: deep links into Explore, whose Tempo and Loki views are the tools' own UIs.

Only operators get them: Grafana isn't tenant-scoped (lattice RFC-0002).
"""

import json
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlencode

from portalr.readers.loki import EVERY_STREAM, RUN_METADATA, TENANT_METADATA
from portalr.readers.query import quoted
from portalr.readers.tempo import TENANT_ATTRIBUTE

TEMPO: Final = "tempo"
"""The Tempo data source's uid, as stackr provisions it."""

LOKI: Final = "loki"
"""The Loki data source's uid, as stackr provisions it."""


@dataclass(frozen=True)
class Grafana:
    """Links into Grafana's Explore.

    Args:
        url: Grafana, as people's browsers reach it.
    """

    url: str

    def _explore(self, datasource: str, query: dict[str, str]) -> str:
        pane = {"datasource": datasource, "queries": [{"refId": "A", **query}]}
        return f"{self.url}/explore?{urlencode({'left': json.dumps(pane)})}"

    def tenant_logs_link(self, tenant: str) -> str:
        """Explore, on a tenant's logs in Loki."""
        return self._explore(
            LOKI, {"expr": f"{EVERY_STREAM} | {TENANT_METADATA} = {quoted(tenant)}"}
        )

    def tenant_traces_link(self, tenant: str) -> str:
        """Explore, on a tenant's traces in Tempo."""
        return self._explore(
            TEMPO,
            {"queryType": "traceql", "query": f"{{ span.{TENANT_ATTRIBUTE} = {quoted(tenant)} }}"},
        )

    def trace_link(self, trace_id: str) -> str:
        """Explore, on a trace in Tempo."""
        return self._explore(TEMPO, {"queryType": "traceql", "query": trace_id})

    def run_logs_link(self, run_id: str) -> str:
        """Explore, on a run's logs in Loki, across tenants."""
        runs = " or ".join(f"{name} = {quoted(run_id)}" for name in RUN_METADATA)
        return self._explore(LOKI, {"expr": f"{EVERY_STREAM} | {runs}"})
