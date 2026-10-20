"""Serving the two built UIs: their files, an index for client-side routes, and their headers."""

from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from portalr.fastapi.site import Site

UIS: Final = ("app", "admin")
"""The two UIs, each built into a directory of its own name."""

HASHED: Final = "assets"
"""The directory Vite writes its hashed files to, which never change under a name."""

IMMUTABLE: Final = "public, max-age=31536000, immutable"
NO_CACHE: Final = "no-cache"


def policy(site: Site) -> str:
    """The policy both UIs share: their own origin, and Supabase Auth for signing in.

    It matters because supabase-js keeps the session in ``localStorage`` (lattice RFC-0002). A
    Supabase project on a path of the application's own origin is already ``'self'``.
    ``'wasm-unsafe-eval'`` lets either UI compile WebAssembly, and ``eval`` stays refused;
    ``scripts/check_wasm.py`` holds what each build ships to ``web/wasm-allowlist.json`` (ADR-0041).
    Where the deployment runs mini apps, ``frame-src`` names their origin alone, so the UIs frame
    nothing else, and their own pages are still framed by no one (lattice RFC-0005).
    """
    supabase = urlsplit(site.supabase_url)
    connect = " ".join(
        ["'self'", *([site.supabase_url] if supabase.scheme in ("http", "https") else [])]
    )
    return "; ".join(
        (
            "default-src 'self'",
            "script-src 'self' 'wasm-unsafe-eval'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src {connect}",
            *([f"frame-src {site.apps}"] if site.apps else []),
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        )
    )


def ui_router(site: Site, root: Path) -> APIRouter:
    """Serve each UI from ``root/<name>``, as Vite built it."""
    router = APIRouter(include_in_schema=False)
    headers = {
        "Content-Security-Policy": policy(site),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    for name in UIS:
        _serve(router, name, (root / name).resolve(), headers)
    return router


def _serve(router: APIRouter, name: str, built: Path, headers: dict[str, str]) -> None:
    def file(path: Path, cache: str) -> Response:
        return FileResponse(path, headers={**headers, "Cache-Control": cache})

    @router.get(f"/{name}")
    async def redirect() -> Response:
        return RedirectResponse(f"{name}/", status_code=308)

    @router.get(f"/{name}/{{path:path}}")
    async def serve(path: str) -> Response:
        try:
            wanted = (built / path).resolve()
        except ValueError:  # a path no file can have, such as one with a NUL
            wanted = built
        hashed = wanted.is_relative_to(built / HASHED)
        if wanted.is_relative_to(built) and wanted.is_file():
            return file(wanted, IMMUTABLE if hashed else NO_CACHE)
        if hashed:
            # An asset that isn't there is missing, not a client-side route.
            raise HTTPException(status_code=404, detail="no such asset")
        index = built / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="this UI isn't built")
        # A client-side route: the UI's index renders it.
        return file(index, NO_CACHE)
