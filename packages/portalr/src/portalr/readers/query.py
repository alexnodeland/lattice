"""The pieces every query is built from: typed parameters, and strings quoted for each language.

No user writes TraceQL, LogQL or PromQL. A reader builds each query from its parameters, and an
id that reaches a query is checked against :data:`ID` first, then quoted.
"""

import json
import re
from datetime import datetime
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

ID: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}")
"""What an id in a query may be: a thread, run, session or trace id."""


def _id(value: str) -> str:
    if not ID.fullmatch(value):
        raise ValueError("not an id")
    return value


type Id = Annotated[str, AfterValidator(_id)]
"""An id a query may name."""


def quoted(value: str) -> str:
    """A string literal for TraceQL, LogQL or PromQL, which all read Go's double-quoted strings."""
    return json.dumps(value)


class Window(BaseModel):
    """A span of time, and how many results to return from it."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    limit: Annotated[int, Field(ge=1, le=1000)] = 100
