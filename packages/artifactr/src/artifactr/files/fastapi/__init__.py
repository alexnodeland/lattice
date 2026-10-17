"""People's check-out and check-in over HTTP, with the `fastapi` extra.

[`files_router`][artifactr.files.fastapi.files_router] is the REST surface, mounted beside
artifactr's own router: check out, extend, check in, download a version and fetch a page.
[`editor_app`][artifactr.files.fastapi.editor_app] serves an app's browser build, as released,
on an origin of its own, under a policy that lets it reach nothing else (lattice RFC-0003,
phase 4).
"""

from artifactr.files.fastapi.editor import editor_app, editor_policy
from artifactr.files.fastapi.router import CheckedIn, FileStatus, Lease, files_router

__all__ = ["CheckedIn", "FileStatus", "Lease", "editor_app", "editor_policy", "files_router"]
