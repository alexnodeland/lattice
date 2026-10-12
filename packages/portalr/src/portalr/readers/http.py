"""One request to a tool, answered as JSON or as :class:`Unavailable`, never as an exception."""

from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from portalr.readers.reading import Unavailable


async def read[T](
    client: httpx.AsyncClient,
    tool: str,
    url: str,
    shape: TypeAdapter[T],
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json: Any = None,
) -> T | Unavailable | None:
    """The tool's answer, in ``shape``; ``None`` if it has nothing there (404); or why neither."""
    try:
        response = await client.request(method, url, params=params, json=json)
    except httpx.HTTPError as error:
        return Unavailable(reason=f"{tool} didn't answer: {type(error).__name__}")
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        return Unavailable(reason=f"{tool} answered {response.status_code}")
    try:
        return shape.validate_json(response.content)
    except ValidationError:
        return Unavailable(reason=f"{tool} answered with something unexpected")
