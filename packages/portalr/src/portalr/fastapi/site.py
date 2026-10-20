"""What the UIs need to know about the application they run in, as ``config.json`` serves it."""

import base64
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from lattice_core.integrations import KEY


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
    editors: dict[str, str] = {}
    """Each native file's hosted editor, by its app's integration, such as ``files:wordcraft``:
    the app's browser build, served over https on an origin of its own, for which the portal sets
    no cookies (lattice RFC-0003); http only on loopback, for tests. The app opens it in a new tab
    when a person checks a file out, and opens none that is on its own origin."""
    apps: str | None = None
    """The origin mini apps run on (lattice RFC-0005), such as ``https://apps.example.com``: a
    host of its own, the same site as the portal's, for which nothing sets or reads a cookie,
    serving the sandbox and nothing else (:class:`~portalr.fastapi.SandboxOrigin`); http only on
    loopback, for development and tests. The portal frames it alone. None where the deployment
    runs no apps: each is shown as its label and summary."""

    @field_validator("apps")
    @classmethod
    def _apps(cls, apps: str | None) -> str | None:
        """Refuse an apps origin that is no web origin of its own; keep it as its origin."""
        if apps is None:
            return None
        parts = urlsplit(apps)
        if not _web(apps):
            raise ValueError(f"mini apps are at {apps}: give them https, or http on loopback")
        if parts.username is not None or parts.password is not None or not parts.hostname:
            raise ValueError(f"mini apps are at {apps}: a host, with no user or password")
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError(f"mini apps are at {apps}: an origin, with no path, query or fragment")
        return f"{parts.scheme}://{parts.netloc}"

    @field_validator("editors")
    @classmethod
    def _editors(cls, editors: dict[str, str]) -> dict[str, str]:
        """Refuse an editor for no native file's app, or one at no web address of its own."""
        for key, url in editors.items():
            if not (key.startswith("files:") and KEY.fullmatch(key)):
                raise ValueError(f"{key} is no native file's app: its key is files:<app>")
            parts = urlsplit(url)
            if not _web(url):
                raise ValueError(f"{key}'s editor is at {url}: give it https, or http on loopback")
            if parts.username is not None or parts.password is not None or not parts.hostname:
                raise ValueError(f"{key}'s editor is at {url}: a host, with no user or password")
        return editors

    @model_validator(mode="after")
    def _editors_apart(self) -> "Site":
        """Refuse an editor on the apps' origin or Supabase's.

        The portal frames an editor with its origin's scripts allowed, so it must be an origin of
        its own. The portal's own origin isn't known here; the UIs refuse an editor on it.
        """
        others = {_origin(url) for url in (self.apps, self.supabase_url) if url and _web(url)}
        for key, url in self.editors.items():
            if _origin(url) in others:
                raise ValueError(f"{key}'s editor is at {url}: give it an origin of its own")
        return self

    @field_validator("supabase_key")
    @classmethod
    def _publishable(cls, key: str) -> str:
        """Refuse a secret key: ``config.json`` is public; a secret key bypasses row security."""
        if key.startswith("sb_secret_") or _role(key) == "service_role":
            raise ValueError("this is a secret key; config.json takes the publishable one")
        return key


def _origin(url: str) -> str:
    """A URL's origin, its scheme and host in lower case."""
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _web(url: str) -> bool:
    """Whether a URL is https, or http on loopback, as a test's or a developer's is."""
    parts = urlsplit(url)
    loopback = parts.hostname in ("localhost", "127.0.0.1", "::1")
    return parts.scheme == "https" or (parts.scheme == "http" and loopback)


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
