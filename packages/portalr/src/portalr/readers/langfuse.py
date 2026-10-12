"""Langfuse: a tenant's feedback and evaluation scores.

Langfuse is read for scores only; traces come from Tempo. Every read filters on the traces'
``tenant:<id>`` tag, which the libraries put on every trace they send.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from portalr.readers.http import read
from portalr.readers.query import Window
from portalr.readers.reading import Ok, Unavailable
from portalr.tenant import Tenant


def tenant_tag(tenant: Tenant) -> str:
    """The trace tag that names the tenant: ``tenant:<id>``."""
    return f"tenant:{tenant.id}"


class Score(BaseModel):
    """A score: a person's feedback, or an evaluator's verdict, on a trace."""

    model_config = ConfigDict(frozen=True)

    id: str
    trace_id: str | None = Field(default=None, validation_alias="traceId")
    name: str
    value: float | None = None
    string_value: str | None = Field(default=None, validation_alias="stringValue")
    source: str | None = None
    timestamp: datetime
    comment: str | None = None


class _Page(BaseModel):
    data: list[Score]


_PAGE: Final = TypeAdapter(_Page)


def parameters(tenant: Tenant, window: Window) -> dict[str, str | int]:
    """The scores API's parameters: the tenant's tag, and the window."""
    return {
        "traceTags": tenant_tag(tenant),
        "fromTimestamp": window.start.isoformat(),
        "toTimestamp": window.end.isoformat(),
        "limit": window.limit,
    }


@dataclass(frozen=True)
class Langfuse:
    """Reads scores from Langfuse's public API.

    Args:
        url: Langfuse, such as ``http://langfuse:3000``; also the base of its deep links.
        project: The project's id, for deep links.
        client: The HTTP client, with the project's public and secret keys as its basic auth.
    """

    url: str
    project: str
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)

    async def scores(self, tenant: Tenant, window: Window) -> Ok[list[Score]] | Unavailable:
        """The tenant's scores in the window, newest first."""
        page = await read(
            self.client,
            "langfuse",
            f"{self.url}/api/public/scores",
            _PAGE,
            params=parameters(tenant, window),
        )
        if page is None or isinstance(page, Unavailable):
            return page or Unavailable(reason="langfuse has no scores API at that address")
        return Ok(data=sorted(page.data, key=lambda score: score.timestamp, reverse=True))

    def trace_link(self, trace_id: str) -> str:
        """Langfuse's page for a trace."""
        return f"{self.url}/project/{self.project}/traces/{trace_id}"

    def session_link(self, session_id: str) -> str:
        """Langfuse's page for a session: an artifactr thread."""
        return f"{self.url}/project/{self.project}/sessions/{session_id}"
