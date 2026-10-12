"""The pieces every query is built from: typed parameters, and strings quoted for each language.

No user writes TraceQL, LogQL or PromQL. A reader builds each query from its parameters. An id
from the request is checked against :data:`ID`, then quoted; the tenant's id is grantr's, which
grantr has checked already, and is quoted.
"""

import json
from datetime import datetime
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ID: Final = r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$"
"""What an id in a query may be: a thread, run, session or trace id, as the document says."""


type Id = Annotated[str, StringConstraints(pattern=ID)]
"""An id a query may name."""


def quoted(value: str) -> str:
    """A string literal for TraceQL, LogQL or PromQL, which all read Go's double-quoted strings."""
    return json.dumps(value, ensure_ascii=False)


class Window(BaseModel):
    """A span of time, and how many results to return from it."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    limit: Annotated[int, Field(ge=1, le=1000)] = 100
