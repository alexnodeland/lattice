"""Serving the two built UIs: their files, an index for client-side routes, and their headers."""

from pathlib import Path
from typing import Final

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
    """The UIs' Content-Security-Policy: their own origin, and Supabase Auth for signing in.

    It matters because supabase-js keeps the session in ``localStorage`` (lattice RFC-0002).
    """
    return "; ".join(
        (
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src 'self' {site.supabase_url}",
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
        wanted = (built / path).resolve()
        if wanted.is_relative_to(built) and wanted.is_file():
            return file(wanted, IMMUTABLE if wanted.is_relative_to(built / HASHED) else NO_CACHE)
        index = built / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404, detail="this UI isn't built")
        # A client-side route: the UI's index renders it.
        return file(index, NO_CACHE)
