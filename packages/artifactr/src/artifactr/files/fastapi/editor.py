"""An app's browser build, served as released, on an origin of its own (lattice RFC-0003).

The build is a static site; nothing of it is changed, only the headers it is served with. Its
policy lets the page run its own files, its inline script by its hash, and its WebAssembly, and
nothing else: no other origin is reached, and no page frames it but, for an app whose build has
a host surface, lattice's shim beside it, which the portal frames (native files ADR-0010). Serve
it on a host name for which the portal sets no cookies, so the editor never sees a token.
"""

import base64
import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from artifactr.files.craft import Craft
from artifactr.files.fastapi.shim import PATH, shim_page, shim_policy

INLINE: Final = re.compile(r"<script\b[^>]*>(.*?)</script\b[^>]*>", re.DOTALL | re.IGNORECASE)
"""An inline script in the page, which the policy allows by the hash of its text."""

IMMUTABLE: Final = (".wasm", ".js")
"""The build's code, named by its hash in WordCraft's build, so cached for good once served;
the page, and anything not found, is revalidated every time."""


def editor_policy(index: str, *, portal: str | None = None) -> str:
    """The Content-Security-Policy for a build whose page is `index`.

    Its own files, and `blob:` for what the page makes itself, such as a saved file; its inline
    scripts by their SHA-256, and WebAssembly compiled from its own bytes, and no other code;
    styles; and no form, base or plugin. Nothing frames it; or, given the `portal` that frames
    the shim, only the shim, of its own origin, inside the portal: a frame's ancestors are each
    checked, the top one too.
    """
    hashes = [
        f"'sha256-{base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()}'"
        for text in INLINE.findall(index)
        if text.strip()
    ]
    return "; ".join(
        [
            "default-src 'self' blob:",
            " ".join(["script-src 'self'", *hashes, "'wasm-unsafe-eval'"]),
            # The build's file picker adds a stylesheet of its own as it opens, whose text is in
            # the WebAssembly; a style runs no code, and what it could load is held to the
            # policy's own sources.
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' blob: data:",
            # Workers, were there any, only from the build's own files: not from blob:.
            "worker-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            f"frame-ancestors {"'none'" if portal is None else f"'self' {portal}"}",
        ]
    )


def editor_app(
    build: Path,
    *,
    bridge: Craft | None = None,
    portal: str | None = None,
    methods: Sequence[str] = (),
) -> ASGIApp:
    """Serve a browser build's directory, as released, under its policy; and its shim, if asked.

    With `bridge` and `portal`, it also serves the shim at `/.lattice/shim.html`, which the
    portal frames to open the checked-out file in the build and hear its saves.

    Args:
        build: The directory holding the build's `index.html`, such as what
            `scripts/craft wordcraft web` prints.
        bridge: The app whose build it is, if its build has a host surface for the shim to reach.
        portal: The portal's origin, the only one that may frame the shim, and that it answers.
        methods: For a build with a JavaScript API, the methods of it the portal may call.

    Raises:
        FileNotFoundError: If the directory has no `index.html`.
        ValueError: If only one of `bridge` and `portal` is given, or the shim can't be made
            for them, or the build has a file where the shim is served.
    """
    index = (build / "index.html").read_text(encoding="utf-8")
    routes: list[Route | Mount] = [Mount("/", StaticFiles(directory=build, html=True))]
    if (bridge is None) != (portal is None):
        raise ValueError("a shim needs both the app it bridges to and the portal that frames it")
    if bridge is not None and portal is not None:
        page, framed = shim_page(bridge, portal, methods), shim_policy(portal)
        if (build / PATH.lstrip("/")).parent.exists():
            raise ValueError(f"the build has files where the shim is served, {PATH}")

        async def shim(_request: Request) -> HTMLResponse:
            return HTMLResponse(page, headers={"Content-Security-Policy": framed})

        routes.insert(0, Route(PATH, shim))
    policy = editor_policy(index, portal=portal)
    static = Starlette(routes=routes)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Security-Policy", policy)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                immutable = message["status"] == 200 and path.endswith(IMMUTABLE)
                cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
                headers["Cache-Control"] = cache
            await send(message)

        await static(scope, receive, send_with_headers)

    return app
