"""The pieces every query is built from: typed parameters, and strings quoted for each language.

No user writes TraceQL, LogQL or PromQL. A reader builds each query from its parameters. An id
from the request is checked against :data:`ID`, then quoted; the tenant's id is grantr's, which
grantr has checked already, and is quoted.
"""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Final, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

ID: Final = r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$"
"""What an id in a query may be: a thread, run, session or trace id, as the document says."""


type Id = Annotated[str, StringConstraints(pattern=ID)]
"""An id a query may name."""


def quoted(value: str) -> str:
    """A string literal for TraceQL, LogQL or PromQL, which all read Go's double-quoted strings."""
    return json.dumps(value, ensure_ascii=False)


EARLIEST: Final = datetime(2000, 1, 1, tzinfo=UTC)
"""The earliest a span may start: before anything the libraries record, and late enough that a
reader may look back from it."""


class Span(BaseModel):
    """A span of time: its start, in 2000 or later, and its end, after it; each with its zone."""

    model_config = ConfigDict(frozen=True)

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.start < EARLIEST:
            raise ValueError(f"a span starts in {EARLIEST.year} or later")
        if self.end <= self.start:
            raise ValueError("a span ends after it starts")
        return self


class Window(Span):
    """A span of time, and how many results to return from it."""

    limit: Annotated[int, Field(ge=1, le=1000)] = 100


def day_of(at: datetime) -> date:
    """The day a moment is in, in UTC."""
    return at.astimezone(UTC).date()


def days_in(span: Span) -> list[date]:
    """Each day the span touches, in UTC, the first first."""
    first, last = day_of(span.start), day_of(span.end - timedelta(microseconds=1))
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]
