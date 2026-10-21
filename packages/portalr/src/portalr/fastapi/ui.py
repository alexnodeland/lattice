"""Serving the two built UIs: their files, an index for client-side routes, and their headers."""

import hashlib
import html
import re
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from portalr.brand.kit import Kit
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
    Where the deployment runs mini apps, ``frame-src`` names their origin, and where it hosts
    native files' editors, each editor's origin, whose shim frames the app's build there (portalr
    ADR-0055): the UIs frame nothing else, and their own pages are still framed by no one
    (lattice RFC-0005).
    """
    supabase = urlsplit(site.supabase_url)
    connect = " ".join(
        ["'self'", *([site.supabase_url] if supabase.scheme in ("http", "https") else [])]
    )
    named: list[str] = [*([site.apps] if site.apps else []), *_origins(site.editors)]
    frames = list(dict.fromkeys(named))
    return "; ".join(
        (
            "default-src 'self'",
            "script-src 'self' 'wasm-unsafe-eval'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            f"connect-src {connect}",
            *([f"frame-src {' '.join(frames)}"] if frames else []),
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        )
    )


def _origins(editors: dict[str, str]) -> list[str]:
    """Each editor's origin, once, in the order they are named."""
    return [f"{parts.scheme}://{parts.netloc}" for parts in map(urlsplit, editors.values())]


def ui_router(site: Site, root: Path) -> APIRouter:
    """Serve each UI from ``root/<name>``, as Vite built it."""
    router = APIRouter(include_in_schema=False)
    headers = {
        "Content-Security-Policy": policy(site),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    for name in UIS:
        _serve(router, name, (root / name).resolve(), headers, site.kit)
    if site.kit is not None:
        _brand(router, site.kit)
    return router


MOUNT: Final = "/portalr"
"""Where an application mounts portalr's router, which the UIs' builds are made for."""

TYPES: Final = {
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}

SVG_POLICY: Final = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
"""What an SVG of a kit may do opened on its own: draw itself, and nothing else."""


def _brand(router: APIRouter, kit: Kit) -> None:
    """Serve a kit's files under its hash, and nothing else: an unknown path or hash is 404."""

    @router.get("/brand/{version}/{path:path}")
    async def brand(version: str, path: str) -> Response:
        data = kit.files.get(path) if version == kit.hash else None
        if data is None:
            raise HTTPException(status_code=404, detail="no such file in the brand kit")
        suffix = Path(path).suffix
        headers = {
            "Cache-Control": IMMUTABLE,
            "X-Content-Type-Options": "nosniff",
            **({"Content-Security-Policy": SVG_POLICY} if suffix == ".svg" else {}),
        }
        return Response(data, media_type=TYPES[suffix], headers=headers)


def branded(index: str, kit: Kit, ui: str) -> str:
    """A UI's index with the kit in place before the first paint.

    Its name in the tab, its icon, its theme colour in each scheme, and its stylesheet after the
    UI's own. Every word is escaped.
    """
    base = f"{MOUNT}/{kit.base}"
    name = html.escape(kit.brand.identity.admin if ui == "admin" else kit.brand.identity.app)
    light, dark = kit.theme
    head = "\n".join(
        (
            f'    <link rel="icon" href="{base}{html.escape(kit.brand.assets.favicon)}" />',
            *(
                f'    <meta name="theme-color" media="(prefers-color-scheme: {scheme})"'
                f' content="{paper}" />'
                for scheme, paper in (("light", light), ("dark", dark))
            ),
            f'    <link rel="stylesheet" href="{base}brand.css" />',
        )
    )
    titled = f"<title>{name}</title>"
    index = re.sub(r"<title>[^<]*</title>", titled, index, count=1)
    # In the head, before its end, or after the title where a page leaves the end implied.
    if "</head>" in index:
        return index.replace("</head>", f"{head}\n  </head>", 1)
    return index.replace(titled, f"{titled}\n{head}", 1)


def _serve(
    router: APIRouter, name: str, built: Path, headers: dict[str, str], kit: Kit | None
) -> None:
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
        # A client-side route: the UI's index renders it, with the brand kit's, if any, in place.
        if kit is None:
            return file(index, NO_CACHE)
        page = branded(index.read_text(), kit, name)
        tag = '"' + hashlib.sha256(page.encode()).hexdigest()[:32] + '"'
        return Response(
            page,
            media_type="text/html; charset=utf-8",
            headers={**headers, "Cache-Control": NO_CACHE, "ETag": tag},
        )
