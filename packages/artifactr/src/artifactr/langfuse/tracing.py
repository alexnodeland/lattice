"""Traces in Langfuse: a span filter that keeps whole traces, and a turn's trace attributes."""

import contextlib
from collections.abc import AsyncGenerator
from typing import Any, Final

from langfuse import propagate_attributes
from langfuse.span_filter import is_default_export_span
from opentelemetry.sdk.trace import ReadableSpan

from artifactr.agent import Session
from artifactr.core import UserActor
from artifactr.telemetry import SCOPE

KEPT_SCOPES: Final = frozenset(
    {
        SCOPE,
        "pydantic-graph",
        "mcp-python-sdk",
        "opentelemetry.instrumentation.fastapi",
        "opentelemetry.instrumentation.asgi",
        "opentelemetry.instrumentation.sqlalchemy",
        "opentelemetry.instrumentation.asyncpg",
        "opentelemetry.instrumentation.httpx",
    }
)
"""Instrumentation scopes whose spans Langfuse keeps, besides its default LLM spans."""

MAX_ATTRIBUTE = 200
"""The longest trace attribute value Langfuse accepts."""


def should_export_span(span: ReadableSpan) -> bool:
    """Return whether Langfuse should export a span: pass it as ``should_export_span``.

    Langfuse's default keeps only LLM spans. This keeps those, and artifactr's, pydantic-graph's,
    the MCP SDK's and the FastAPI, SQLAlchemy, asyncpg and httpx instrumentations', so a turn's
    trace is whole: its commits, database queries and HTTP calls around the model calls.
    """
    scope = span.instrumentation_scope.name if span.instrumentation_scope else ""
    kept = any(scope == name or scope.startswith(f"{name}.") for name in KEPT_SCOPES)
    return kept or is_default_export_span(span)


async def turn_attributes(session: Session[Any]) -> dict[str, Any]:
    """Return a turn's Langfuse trace attributes, within Langfuse's limits.

    The session is the thread; the user is the person whose message or answer started the
    turn; the tags name the tenant, the workspace and the kinds of artifact the thread
    follows; the metadata holds artifactr's ids. Values are ASCII and at most 200 characters.
    """
    workspace = session.workspace
    thread = await workspace.thread(session.thread_id)
    kinds = sorted({(await workspace.artifact(a)).kind for a in thread.focus})
    person = session.requested_by
    return {
        "session_id": _limit(session.thread_id),
        "user_id": _limit(person.id) if isinstance(person, UserActor) else None,
        "trace_name": "turn",
        "tags": [
            _limit(f"tenant:{workspace.tenant_id}"),
            _limit(f"workspace:{workspace.workspace_id}"),
            *(_limit(f"kind:{kind}") for kind in kinds),
        ],
        "metadata": {
            key: _limit(value)
            for key, value in {
                "tenant_id": workspace.tenant_id,
                "workspace_id": workspace.workspace_id,
                "thread_id": session.thread_id,
                "run_id": session.run_id,
                "trigger": session.trigger,
            }.items()
        },
    }


@contextlib.asynccontextmanager
async def langfuse_turn(session: Session[Any]) -> AsyncGenerator[None]:
    """Propagate a turn's trace attributes to Langfuse; a ``TurnContext`` for the ``Runner``.

    The attributes are set on the turn's span and every span in the turn, so Langfuse files the
    trace under its session and user, with its tags and metadata.
    """
    with propagate_attributes(**await turn_attributes(session)):
        yield


def _limit(value: str) -> str:
    """Make a value acceptable to Langfuse: ASCII, and at most 200 characters."""
    return value.encode("ascii", "replace").decode("ascii")[:MAX_ATTRIBUTE]
