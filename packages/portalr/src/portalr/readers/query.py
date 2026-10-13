"""The pieces every query is built from: typed parameters, and strings quoted for each language.

No user writes TraceQL, LogQL or PromQL. A reader builds each query from its parameters. An id
from the request is checked against :data:`ID`, then quoted; the tenant's id is grantr's, which
grantr has checked already, and is quoted.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Final, Self

from pydantic import (
    AfterValidator,
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


def _in_utc(at: datetime) -> datetime:
    """A moment given with no zone, as one in UTC, so every moment compares with every other."""
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)


type Moment = Annotated[datetime, AfterValidator(_in_utc)]
"""A moment: in UTC where it was given with no zone."""


class Span(BaseModel):
    """A span of time: its start, and its end, after it."""

    model_config = ConfigDict(frozen=True)

    start: Moment
    end: Moment

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.end <= self.start:
            raise ValueError("a span ends after it starts")
        return self


class Window(Span):
    """A span of time, and how many results to return from it."""

    limit: Annotated[int, Field(ge=1, le=1000)] = 100
