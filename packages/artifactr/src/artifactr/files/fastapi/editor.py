"""An app's browser build, served as released, on an origin of its own (lattice RFC-0003).

The build is a static site; nothing of it is changed, only the headers it is served with. Its
policy lets the page run its own files, its inline script by its hash, and its WebAssembly, and
nothing else: no other origin is reached, and no page frames it. Serve it on a
host name for which the portal sets no cookies, so the editor never sees a token.
"""

import base64
import hashlib
import re
from pathlib import Path
from typing import Final

from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

INLINE: Final = re.compile(r"<script\b[^>]*>(.*?)</script\b[^>]*>", re.DOTALL | re.IGNORECASE)
"""An inline script in the page, which the policy allows by the hash of its text."""

IMMUTABLE: Final = (".wasm", ".js")
"""The build's code, named by its hash in WordCraft's build, so cached for good once served;
the page, and anything not found, is revalidated every time."""


def editor_policy(index: str) -> str:
    """The Content-Security-Policy for a build whose page is `index`.

    Its own files, and `blob:` for what the page makes itself, such as a saved file; its inline
    scripts by their SHA-256, and WebAssembly compiled from its own bytes, and no other code;
    styles; and no frame, form, base or plugin.
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
            "frame-ancestors 'none'",
        ]
    )


def editor_app(build: Path) -> ASGIApp:
    """Serve a browser build's directory, as released, under its policy.

    Args:
        build: The directory holding the build's `index.html`, such as what
            `scripts/wordcraft web` prints.

    Raises:
        FileNotFoundError: If the directory has no `index.html`.
    """
    policy = editor_policy((build / "index.html").read_text(encoding="utf-8"))
    static = Starlette(routes=[Mount("/", StaticFiles(directory=build, html=True))])

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = policy
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
