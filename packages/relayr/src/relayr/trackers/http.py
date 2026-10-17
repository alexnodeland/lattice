"""What the adapters share: a request to a tracker's REST API, its failures as the port's errors.

It needs httpx, which the `plane` and `vikunja` extras install; `relayr.trackers` itself doesn't
import it.
"""

from collections.abc import Collection, Mapping
from typing import Any, Final

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from relayr.trackers.port import NotFound, RateLimited, Refused, Unauthorized, Unavailable

TIMEOUT: Final = 10.0
"""How many seconds each phase of a request may take (connecting, writing, reading); the writes
under one claim are bounded together, by `relayr.trackers.WRITING`."""


class Api:
    """Requests to one tracker's REST API, with one tenant's key.

    Args:
        client: The HTTP client, which the application shares and closes.
        base_url: Where the API is, such as `https://plane.example.com/api/v1`.
        headers: What every request carries: the key, as the tracker takes it.
    """

    def __init__(
        self, client: httpx.AsyncClient, base_url: str, headers: Mapping[str, str]
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        answered: Collection[int] = (),
    ) -> httpx.Response:
        """Make a request; return its response if it succeeded or its status is `answered`.

        Raises:
            Unavailable: If the tracker didn't answer within the timeout, or failed.
            RateLimited: On 429, with its `Retry-After`.
            Unauthorized: On 401 or 403: the key can't do this.
            NotFound: On 404.
            Refused: On any other status from 400, with the tracker's message.
        """
        try:
            response = await self._client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json,
                headers=self._headers,
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as error:
            raise Unavailable(f"the tracker didn't answer: {type(error).__name__}") from error
        status = response.status_code
        if status < 400 or status in answered:
            return response
        message = _message(response)
        if status == 429:
            raise RateLimited(_seconds(response.headers.get("retry-after")))
        if status in (401, 403):
            raise Unauthorized(message)
        if status == 404:
            raise NotFound(message)
        if status >= 500:
            raise Unavailable(message)
        raise Refused(message)


class _Said(BaseModel):
    """A tracker's error body, as far as it says something plainly."""

    model_config = ConfigDict(extra="ignore")

    error: str | None = None
    detail: str | None = None
    message: str | None = None


def _message(response: httpx.Response) -> str:
    """What a tracker says went wrong: Plane's `error` or `detail`, or Vikunja's `message`."""
    try:
        said = _Said.model_validate_json(response.content)
    except ValidationError:
        return f"{response.status_code}: {response.text[:200]}"
    return (
        said.error
        or said.detail
        or said.message
        or f"{response.status_code}: {response.text[:200]}"
    )


def _seconds(retry_after: str | None) -> float | None:
    """`Retry-After` in seconds, if it says so; its HTTP-date form is taken as unsaid."""
    try:
        return float(retry_after) if retry_after is not None else None
    except ValueError:
        return None
