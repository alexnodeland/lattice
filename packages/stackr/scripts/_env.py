"""Read stackr's `KEY=VALUE` files: `.env`, `.env.example` and `versions.env`.

The scripts import this from their own directory, which Python puts on `sys.path`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")


def read_env(path: Path) -> dict[str, str]:
    """A file's `KEY=VALUE` lines, in order, or none when the file is missing."""
    if not path.exists():
        return {}
    matches = (LINE.match(line.strip()) for line in path.read_text().splitlines())
    return {match["key"]: match["value"] for match in matches if match}


def settings() -> dict[str, str]:
    """The stack's settings: `.env`'s, or `.env.example`'s where `.env` leaves one unset or empty.

    `.env.example` gives values only for the settings it doesn't generate, such as the published
    ports; for a secret it has a `generate:...` placeholder, which only `.env` replaces. Compose's
    `${KEY:-default}` reads an empty value as unset too, and its defaults are `.env.example`'s.
    """
    local = read_env(ROOT / ".env")
    return read_env(ROOT / ".env.example") | {key: value for key, value in local.items() if value}


def published_host(env: dict[str, str]) -> str:
    """The host the stack's published ports are reached at.

    That is `STACKR_BIND`, or this machine when it binds every interface.
    """
    bind = env["STACKR_BIND"]
    return "127.0.0.1" if bind == "0.0.0.0" else bind
