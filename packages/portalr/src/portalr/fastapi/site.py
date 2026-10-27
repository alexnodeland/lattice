"""What the UIs need to know about the application they run in, as ``config.json`` serves it."""

import base64
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator, model_validator

from lattice_core.integrations import KEY
from lattice_core.origins import web_origin
from portalr.brand.kit import Kit, load
from portalr.brand.tokens import BrandError


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


class Place(BaseModel):
    """Where mini apps and the editors are for a portal reached at one of its other origins.

    A deployment reached at several addresses, such as this machine's loopback and its tailnet
    name, is several portal origins (portalr ADR-0083). The sandbox and each editor are framed
    from the portal, so each portal origin needs its own, reachable from the same place: the
    sandbox's and the editors' origins beside that portal origin, which ``beside`` derives.
    """

    model_config = ConfigDict(frozen=True)

    apps: str | None = None
    """The origin mini apps run on, for a portal at this origin; None where it runs none."""
    editors: dict[str, str] = {}
    """Each native file's hosted editor, by its app's integration, for a portal at this origin."""

    @field_validator("apps")
    @classmethod
    def _apps(cls, apps: str | None) -> str | None:
        return _apps_origin(apps)

    @field_validator("editors")
    @classmethod
    def _editors(cls, editors: dict[str, str]) -> dict[str, str]:
        return _editor_urls(editors)


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
    brand: Path | None = None
    """The folder of the deployment's brand kit (lattice RFC-0007), which is read and checked when
    the site is made, as the application starts, so a kit with a fault fails the start with every
    fault listed; None for portalr's own look. The kit, read, is :attr:`kit`."""
    _kit: Kit | None = PrivateAttr(default=None)
    apps: str | None = None
    """The origin mini apps run on (lattice RFC-0005), such as ``https://apps.example.com``: a
    host of its own, the same site as the portal's, for which nothing sets or reads a cookie,
    serving the sandbox and nothing else (:class:`~portalr.fastapi.SandboxOrigin`); http only on
    loopback, for development and tests. The portal frames it alone. None where the deployment
    runs no apps: each is shown as its label and summary."""
    origin: str | None = None
    """The portal's own origin, such as ``https://app.example.com``, where the application knows
    it: ``config.json`` carries it, so the UIs can tell an address the deployment doesn't serve
    apps or editors at from one it does. None leaves them trusting the address they are at."""
    aliases: dict[str, Place] = {}
    """Each other origin the portal is reached at, such as its tailnet name beside its loopback
    address, and where mini apps and the editors are for a portal there (portalr ADR-0083): at
    the same host as that portal origin, on the apps' and the editors' own ports, as
    :func:`beside` derives them. The UIs at an origin named here use its place; at the portal's
    own, the canonical ``apps`` and ``editors``; and the portal's policy frames them all."""

    @model_validator(mode="after")
    def _read_kit(self) -> "Site":
        """Read and check the brand kit, or refuse the site with every fault the kit has."""
        if self.brand is not None:
            try:
                self._kit = load(self.brand)
            except BrandError as error:
                message = f"the brand kit at {self.brand} isn't one portalr can serve:\n{error}"
                raise ValueError(message) from error
        return self

    @property
    def kit(self) -> Kit | None:
        """The deployment's brand kit, read and checked; None for portalr's own look."""
        return self._kit

    @field_validator("apps")
    @classmethod
    def _apps(cls, apps: str | None) -> str | None:
        """Refuse an apps origin that is no web origin of its own; keep it as its origin."""
        return _apps_origin(apps)

    @field_validator("editors")
    @classmethod
    def _editors(cls, editors: dict[str, str]) -> dict[str, str]:
        """Refuse an editor for no native file's app, or one at no web address of its own."""
        return _editor_urls(editors)

    @field_validator("origin")
    @classmethod
    def _origin(cls, origin: str | None) -> str | None:
        return None if origin is None else web_origin(origin, what="the portal")

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, aliases: dict[str, Place]) -> dict[str, Place]:
        """Each alias by its portal origin as a browser compares it, which is how the UIs look."""
        named: dict[str, Place] = {}
        for portal, place in aliases.items():
            origin = web_origin(portal, what="the portal")
            if origin in named:
                raise ValueError(f"the portal at {origin} is aliased twice")
            named[origin] = place
        return named

    @model_validator(mode="after")
    def _editors_apart(self) -> "Site":
        """Refuse an editor on the apps' origin, Supabase's or the portal's, for each place.

        The portal frames an editor with its origin's scripts allowed, so it must be an origin of
        its own. The portal's own origin is known here only where ``origin`` says it, and an
        alias's by its key; the UIs refuse an editor on their own origin in any case.
        """
        places = [
            (self.origin, self.apps, self.editors),
            *((portal, place.apps, place.editors) for portal, place in self.aliases.items()),
        ]
        for portal, apps, editors in places:
            named = (portal, apps, self.supabase_url)
            others = {_origin_of(url) for url in named if url} - {None}
            for key, url in editors.items():
                if _origin_of(url) in others:
                    raise ValueError(f"{key}'s editor is at {url}: give it an origin of its own")
        return self

    @field_validator("supabase_key")
    @classmethod
    def _publishable(cls, key: str) -> str:
        """Refuse a secret key: ``config.json`` is public; a secret key bypasses row security."""
        if key.startswith("sb_secret_") or _role(key) == "service_role":
            raise ValueError("this is a secret key; config.json takes the publishable one")
        return key


def beside(portal: str, extra: str, *, apps: str | None, editors: dict[str, str]) -> Place:
    """Where mini apps and the editors are for the portal reached at `extra`, beside `portal`.

    The rule is the port's: an application on one machine serves the portal, the sandbox and
    each editor on ports of its own, and an address that reaches the machine under another
    name, such as its tailnet name forwarding each port, reaches each on the same port. So the
    apps' origin beside `extra` is `extra`'s scheme and host on the canonical apps origin's port,
    and each editor's address likewise, its path kept.

    Args:
        portal: The portal's own origin, which `extra` is another address of.
        extra: The portal's other origin, such as ``https://my-machine.my-tailnet.ts.net``.
        apps: The canonical apps origin, with its port, such as ``http://127.0.0.1:8801``; None
            where the deployment runs no apps.
        editors: The canonical editors, each with its port, such as ``http://127.0.0.1:8802/``.

    Raises:
        ValueError: If `extra` is `portal` itself, or the apps origin or an editor has no port
            of its own to carry over, as one at an edge on the default port hasn't: name that
            deployment's places yourself.
    """
    own, other = web_origin(portal, what="the portal"), web_origin(extra, what="the portal")
    if own == other:
        raise ValueError(f"{other} is the portal's own origin, not another address of it")
    at = urlsplit(other)

    def moved(url: str, what: str) -> str:
        parts = urlsplit(url)
        if parts.port is None:
            raise ValueError(f"{what} is at {url}, with no port of its own to reach beside {other}")
        host = f"[{at.hostname}]" if ":" in (at.hostname or "") else at.hostname
        return urlunsplit((at.scheme, f"{host}:{parts.port}", parts.path, "", ""))

    origin = _apps_origin(apps)
    return Place(
        apps=None if origin is None else moved(origin, "mini apps"),
        editors={key: moved(url, f"{key}'s editor") for key, url in _editor_urls(editors).items()},
    )


def _apps_origin(apps: str | None) -> str | None:
    """Mini apps' origin as a browser compares it, or a refusal naming them."""
    return None if apps is None else web_origin(apps, what="mini apps")


def _editor_urls(editors: dict[str, str]) -> dict[str, str]:
    """The editors as given, each for a native file's app and on a web origin of its own."""
    for key, url in editors.items():
        if not (key.startswith("files:") and KEY.fullmatch(key)):
            raise ValueError(f"{key} is no native file's app: its key is files:<app>")
        parts = urlsplit(url)
        # An editor is a URL, which may have a path; its origin is what must be a web origin.
        web_origin(urlunsplit((parts.scheme, parts.netloc, "", "", "")), what=f"{key}'s editor")
    return editors


def _origin_of(url: str) -> str | None:
    """A URL's web origin as a browser compares it, or None where it has none, as a path hasn't."""
    parts = urlsplit(url)
    try:
        return web_origin(urlunsplit((parts.scheme, parts.netloc, "", "", "")))
    except ValueError:
        return None


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
