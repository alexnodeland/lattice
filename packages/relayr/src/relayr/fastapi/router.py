"""The trackers' webhooks: a nudge that makes a bound project's follower poll now.

A webhook carries nothing relayr uses: the follower reads the change itself (lattice RFC-0004).
The route is unauthenticated, so it gives nothing away. A body over `MAX_BODY` is refused once
it says so, or once that much is read; a signature is checked against the tenant's secret the
followers already hold, before anything else is asked, so a flood of requests reaches neither
the secrets nor the tracker. An unknown tenant, a switched-off workspace and a bad signature are
the same 401.
"""

from typing import Annotated, Final

from fastapi import APIRouter, Path, Request, Response
from fastapi.responses import JSONResponse

from lattice_core.commands import calls_none
from lattice_core.refusals import Refused, refusals
from relayr.trackers import TrackerFollowers

MAX_BODY: Final = 1024 * 1024
"""The largest webhook body read, in bytes: 1 MB."""

PathId = Annotated[str, Path(min_length=1)]


def tracker_router(followers: TrackerFollowers) -> APIRouter:
    """Return the router the trackers' webhooks are registered to, for a tenant and a tracker.

    Args:
        followers: The followers a verified webhook wakes, whose credentials verify it.
    """
    router = APIRouter(tags=["relayr"], responses=refusals(401, 413))

    @router.post(
        "/relayr/v1/trackers/{tenant}/{tracker}",
        status_code=204,
        summary="Nudge a tracker project's follower",
        openapi_extra=calls_none(
            "a tracker's webhook, verified by its signature: no person's action"
        ),
    )
    async def nudge(tenant: PathId, tracker: PathId, request: Request) -> Response:
        """Verify a tracker's webhook, and make the followers of the project it names poll now."""
        body = await _read(request)
        if body is None:
            return _refused(413, "the body is larger than relayr reads")
        if not await followers.nudge(tenant, tracker, request.headers, body):
            return _refused(401, "the webhook did not verify")
        return Response(status_code=204)

    return router


async def _read(request: Request) -> bytes | None:
    """The request's body, or None if it says or proves larger than `MAX_BODY`, unread past it."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        return None
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return None
    return bytes(body)


def _refused(status: int, message: str) -> JSONResponse:
    return JSONResponse(Refused(detail=message).model_dump(), status_code=status)
