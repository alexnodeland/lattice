"""The worker: an app's four calls, over HTTP, one job at a time, under limits on each.

It is the one process that reads hostile files. The application sends it each call, with the
token the deployment generated; it runs the call through the app it was given, whose CLI it starts
under [`Limits.launcher`][artifactr.files.worker.Limits.launcher], and replies with what came
back or how it failed. A call waits its turn within its own deadline, so a worker never runs two
jobs at once: it scales by adding containers (lattice RFC-0003).
"""

import hmac
from collections.abc import Awaitable, Callable

import anyio
from pydantic import BaseModel, TypeAdapter, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from artifactr.files.app import App, AppFailed, CommandSpec
from artifactr.files.craft import CRAFTS
from artifactr.files.worker.limits import Limits
from artifactr.files.worker.wire import (
    CALL,
    AppliedReply,
    ApplyCall,
    CommandsCall,
    Failed,
    Hello,
    InspectCall,
    RenderCall,
)

_SPECS = TypeAdapter(list[CommandSpec])


def worker_app(
    app: App,
    *,
    token: str,
    limits: Limits,
    build: str | None = None,
    sweep: Callable[[], object] | None = None,
) -> Starlette:
    """The worker's HTTP application, over an app whose CLI is started under `limits`.

    Args:
        app: The app, made with `launcher=limits.launcher()` and `limit=limits.files`.
        token: What every request's `Authorization: Bearer` must be; any other is 401.
        limits: The deadlines and sizes each call is held to.
        build: The digest of the image the worker runs in, which provenance records.
        sweep: What clears the worker's container after each call, before the next is taken:
            `artifactr.files.worker.sweep.sweep`, where the worker is alone in it. If it fails,
            the call fails as `crashed`, and the worker answers every request after it, its
            health check's too, with 503: it takes no other call until it is restarted.

    Raises:
        ValueError: If the token is empty, which would admit anyone, or the limits give the app's
            CLI less address space than it needs.
    """
    if not token:
        raise ValueError("the worker needs a token: an empty one would admit anyone")
    needed = CRAFTS[app.name].memory if app.name in CRAFTS else 0
    if limits.memory < needed:
        raise ValueError(
            f"{app.name} needs an address space of {needed} bytes; the limits give {limits.memory}"
        )
    hello = Hello(
        name=app.name,
        version=app.version,
        build=build,
        talk=app.talk,
        integration=app.integration,
    )
    turn = anyio.Lock()
    broken: list[str] = []
    """Why the sweep failed, once it has: then the worker serves nothing more."""

    def guarded(
        handle: Callable[[Request], Awaitable[Response]],
    ) -> Callable[[Request], Awaitable[Response]]:
        async def endpoint(request: Request) -> Response:
            if broken:
                return JSONResponse(
                    Failed(failure="crashed", message=broken[0]).model_dump(), status_code=503
                )
            scheme, _, given = request.headers.get("authorization", "").partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(
                given.encode(), token.encode()
            ):
                return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
            try:
                return await handle(request)
            except AppFailed as failed:
                reply = Failed(failure=failed.failure, message=str(failed).partition(": ")[2])
            except ValidationError as error:
                # What the app returned can't be told as a reply: the app's fault, not the call's.
                reply = Failed(failure="crashed", message=f"the reply is not one: {error!r}")
            return JSONResponse(reply.model_dump(), status_code=422)

        return endpoint

    async def take[T](deadline: float, work: Callable[[float], Awaitable[T]]) -> T:
        """Wait for the worker's turn, then do the work in what is left of the deadline."""
        started = anyio.current_time()
        with anyio.move_on_after(deadline) as waiting:
            await turn.acquire()
        try:
            left = deadline - (anyio.current_time() - started)
            if waiting.cancelled_caught or left <= 0:
                raise AppFailed("timeout", f"the worker was busy for more than {deadline:.3g}s")
            return await work(left)
        finally:
            if not waiting.cancelled_caught:
                try:
                    if sweep is not None:
                        with anyio.CancelScope(shield=True):
                            await anyio.to_thread.run_sync(sweep)
                except Exception as error:
                    broken.append(f"the worker couldn't clear itself after a call: {error}")
                    raise AppFailed("crashed", broken[0]) from error
                finally:
                    turn.release()

    async def hi(_request: Request) -> Response:
        return JSONResponse(hello.model_dump())

    async def apply(request: Request) -> Response:
        call = _call(request, ApplyCall)
        source = await _body(request, limits.files) or None
        deadline = min(call.deadline, limits.edit)
        applied = await take(deadline, lambda left: app.apply(source, call.commands, deadline=left))
        reply = AppliedReply(content=applied.content, inspection=applied.inspection)
        return _sized(reply.model_dump_json().encode(), "application/json", limits.reply)

    async def inspect(request: Request) -> Response:
        call = _call(request, InspectCall)
        source = await _body(request, limits.files)
        deadline = min(call.deadline, limits.edit)
        inspection = await take(deadline, lambda left: app.inspect(source, deadline=left))
        return _sized(inspection.model_dump_json().encode(), "application/json", limits.reply)

    async def render(request: Request) -> Response:
        call = _call(request, RenderCall)
        source = await _body(request, limits.files)
        deadline = min(call.deadline, limits.render)
        png = await take(
            deadline,
            lambda left: app.render(source, call.page, scale=call.scale, deadline=left),
        )
        return _sized(png, "image/png", limits.reply)

    async def commands(request: Request) -> Response:
        call = _call(request, CommandsCall)
        specs = await take(limits.edit, lambda _left: app.commands(call.query))
        return _sized(_SPECS.dump_json(list(specs)), "application/json", limits.reply)

    return Starlette(
        routes=[
            Route("/", guarded(hi), methods=["GET"]),
            Route("/apply", guarded(apply), methods=["POST"]),
            Route("/inspect", guarded(inspect), methods=["POST"]),
            Route("/render", guarded(render), methods=["POST"]),
            Route("/commands", guarded(commands), methods=["POST"]),
        ]
    )


def _call[C: BaseModel](request: Request, model: type[C]) -> C:
    """The call in the request's header, refused if it isn't one."""
    try:
        return model.model_validate_json(request.headers.get(CALL, ""))
    except ValidationError as error:
        raise AppFailed("refused", f"the call is not one: {error.error_count()} errors") from None


async def _body(request: Request, limit: int) -> bytes:
    """The request's body, refused as too large past the limit before it is all read."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise AppFailed("too_large", f"the file is larger than {limit} bytes")
    return bytes(body)


def _sized(content: bytes, media_type: str, limit: int) -> Response:
    """A reply of the content, refused as too large past the limit."""
    if len(content) > limit:
        raise AppFailed("too_large", f"the reply is larger than {limit} bytes")
    return Response(content, media_type=media_type)
