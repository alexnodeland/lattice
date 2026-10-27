"""Mini apps' sandbox, on an origin of its own (lattice RFC-0005, portalr ADR-0051).

An agent's app runs in two frames. The portal frames the sandbox, one static page served here on
the apps' origin, which holds nothing: no cookie is set or read for it, and nothing else is
served from it. The sandbox runs the app in a frame of its own, sandboxed to an opaque origin,
under the same policy as itself: nothing is loaded from anywhere, no frame is navigated, and
inline script and style alone run. The app inherits that policy, and the sandbox repeats it in
the app's own document, so neither can be loosened.

Add :class:`SandboxOrigin` to the application, and name the origin in :class:`Site`'s ``apps``,
so the portal frames it and nothing else. A portal reached at several origins, each with an
apps origin beside it (portalr ADR-0084, :class:`Site`'s ``aliases``), gives it every apps
origin, which it answers alike, and every portal origin, which alone may frame it.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from lattice_core.origins import web_origins
from portalr.fastapi.router import UI

__all__ = ["APP_POLICY", "SandboxOrigin", "sandbox_policy"]

APP_POLICY: Final = "; ".join(
    (
        "default-src 'none'",
        "script-src 'unsafe-inline'",
        "style-src 'unsafe-inline'",
        "img-src data:",
        "font-src data:",
        "base-uri 'none'",
        "form-action 'none'",
    )
)
"""What an app may do, and the sandbox with it: inline script and style, ``data:`` images and
fonts, and nothing else. ``default-src 'none'`` refuses every fetch, socket, worker and frame,
and so a frame's navigation too; with no ``'wasm-unsafe-eval'``, WebAssembly is never compiled.
The sandbox's own script is inline, not allowed by its hash: the app's frame inherits this policy,
and a hash would refuse the app's scripts as well. The sandbox puts no untrusted markup in its own
page, so allowing inline script there costs nothing. ``web/ui/csp/app-policy.txt`` holds it for
the sandbox's own copy and for the CSP tests."""

PERMISSIONS: Final = ", ".join(
    f"{feature}=()"
    for feature in (
        "camera",
        "microphone",
        "geolocation",
        "display-capture",
        "payment",
        "usb",
        "serial",
        "bluetooth",
        "hid",
        "clipboard-read",
        "clipboard-write",
        "fullscreen",
        "publickey-credentials-get",
    )
)
"""The powerful features neither frame may ask for, whatever an app tries."""


def sandbox_policy(portal: str | Sequence[str]) -> str:
    """The sandbox's policy: an app's, and framed by the portal's origin alone, or each of them."""
    return f"{APP_POLICY}; frame-ancestors {' '.join(web_origins(portal, what='the portal'))}"


class SandboxOrigin:
    """Serve mini apps' sandbox to requests for the apps' origin, and the application to the rest.

    The sandbox is served at ``/`` alone, under :func:`sandbox_policy`, never cached, sniffed or
    referred, with no powerful feature allowed and no DNS prefetched; anything else asked of the
    apps' origin is not found, and nothing from the application reaches it.

    Args:
        app: The application.
        apps: The apps' origin, as :class:`Site`'s ``apps`` names it; or each of them, with
            those of the site's ``aliases``, answered alike.
        portal: The portal's origin, the only one that may frame the sandbox; or each of them.
        root: The directory the UIs were built into, which holds ``sandbox/index.html``.

    Raises:
        ValueError: If an apps' origin is a portal's: each must be one of its own; or one of
            them is no web origin.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        apps: str | Sequence[str],
        portal: str | Sequence[str],
        root: Path = UI,
    ) -> None:
        self._app = app
        origins = web_origins(apps, what="mini apps")
        portals = web_origins(portal, what="the portal")
        self._hosts = {_host(urlsplit(each).netloc) for each in origins}
        for each in origins:
            if each in portals:
                raise ValueError(f"mini apps at {each} would share a portal's origin")
        self._page = root / "sandbox" / "index.html"
        self._headers = {
            "Content-Security-Policy": sandbox_policy(portal),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-DNS-Prefetch-Control": "off",
            "Permissions-Policy": PERMISSIONS,
            "Cache-Control": "no-cache",
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer a request for the apps' origin here, and pass every other to the application."""
        asked = dict(scope.get("headers", [])).get(b"host", b"").decode("latin-1")
        if scope["type"] not in ("http", "websocket") or _host(asked) not in self._hosts:
            await self._app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await self._answer(scope)(scope, receive, send)

    def _answer(self, scope: Scope) -> Response:
        if scope["path"] != "/":
            return PlainTextResponse("Nothing is served here.", 404, headers=self._headers)
        if scope["method"] not in ("GET", "HEAD"):
            return PlainTextResponse("Only read here.", 405, headers=self._headers)
        if not self._page.is_file():
            return PlainTextResponse("The sandbox isn't built.", 404, headers=self._headers)
        return Response(self._page.read_bytes(), headers=self._headers, media_type="text/html")


def _host(authority: str) -> str:
    """A host and its port as a browser sends them in ``Host``: the default ports left out.

    The scheme isn't asked: behind an edge that ends TLS, the application hears https as http.
    """
    host = authority.lower()
    for default in (":80", ":443"):
        host = host.removesuffix(default)
    return host
