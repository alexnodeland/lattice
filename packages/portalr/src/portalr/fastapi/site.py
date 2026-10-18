"""What the UIs need to know about the application they run in, as ``config.json`` serves it."""

import base64

from pydantic import BaseModel, ConfigDict, field_validator


class Surfaces(BaseModel):
    """Where the application mounts each router, as the UIs' client calls them."""

    model_config = ConfigDict(frozen=True)

    artifactr: str = "/artifactr/v1"
    reflexr: str = "/reflexr/v1"
    grantr: str = ""
    """The origin grantr's router is mounted at: its paths carry ``/grantr/v1`` themselves."""
    portalr: str = "/portalr/v1"
    relayr: str | None = None
    """The origin relayr's tracker reads are mounted at, whose paths carry ``/relayr/v1``
    themselves; None where the application has no tracker, so the UIs never ask."""


class Site(BaseModel):
    """The application's Supabase project, as the UIs sign in to it, and its surfaces.

    The same built UIs serve every deployment: what differs is here.
    """

    model_config = ConfigDict(frozen=True)

    supabase_url: str
    """The project's URL, or a path on the application's own origin that leads to it."""
    supabase_key: str
    """The project's publishable key, which the browser sends with every Supabase Auth call."""
    surfaces: Surfaces = Surfaces()

    @field_validator("supabase_key")
    @classmethod
    def _publishable(cls, key: str) -> str:
        """Refuse a secret key: ``config.json`` is public; a secret key bypasses row security."""
        if key.startswith("sb_secret_") or _role(key) == "service_role":
            raise ValueError("this is a secret key; config.json takes the publishable one")
        return key


def _role(key: str) -> str | None:
    """The ``role`` claim of a legacy JWT key, or None if the key isn't one."""
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        return _Claims.model_validate_json(payload).role
    except ValueError:  # not base64, not JSON, or not an object
        return None


class _Claims(BaseModel):
    role: str | None = None
