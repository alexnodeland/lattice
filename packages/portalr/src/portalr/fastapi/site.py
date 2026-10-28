"""What the UIs need to know about the application they run in, as ``config.json`` serves it."""

import base64
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator, model_validator

from lattice_core.integrations import KEY
from lattice_core.origins import web_origin
from portalr.brand.kit import Kit, load
from portalr.brand.tokens import BrandError

ALIASES = 8
"""The most other origins a portal may be reached at: a policy naming many is a mistake."""


EDITOR_PATH = re.compile(r"(/(?!\.\.?(?:/|$))[A-Za-z0-9._~\-]+)*/?")
"""An editor's path: nothing a policy or a header separates on, nor an escape, nor an empty,
``.`` or ``..`` segment."""


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
    name, is several portal origins (portalr ADR-0084). The sandbox and each editor are framed
    from the portal, so each portal origin needs its own, reachable from the same place: the
    sandbox's and the editors' origins beside that portal origin, which ``beside`` derives.
    """

    model_config = ConfigDict(frozen=True)

    apps: str | None = None
    """The origin mini apps run on, for a portal at this origin; None where it runs none."""
    editors: dict[str, str] = {}
    """Each native file's hosted editor, by its app's integration, for a portal at this origin."""
    links: dict[str, str] = {}
    """Each connected app's address, by its integration, for a portal at this origin."""

    @field_validator("apps")
    @classmethod
    def _apps(cls, apps: str | None) -> str | None:
        return _apps_origin(apps)

    @field_validator("editors")
    @classmethod
    def _editors(cls, editors: dict[str, str]) -> dict[str, str]:
        return _editor_urls(editors)

    @field_validator("links")
    @classmethod
    def _links(cls, links: dict[str, str]) -> dict[str, str]:
        return _link_urls(links)


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
    links: dict[str, str] = {}
    """Each connected app's address, by the integration that brings it, such as
    ``tracker:plane``: a sidecar app with a UI of its own, such as Plane or an editor, which the
    admin opens beside the integration's switch and the palette lists where the integration is on
    in the workspace, each in a new tab (portalr ADR-0088). Each is held to the editors' rule: a
    web origin of its own, a path at most; and none signs in through the portal."""
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
    address, and where mini apps and the editors are for a portal there (portalr ADR-0084): at
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

    @field_validator("links")
    @classmethod
    def _links(cls, links: dict[str, str]) -> dict[str, str]:
        """Refuse a link with no valid integration key, or at no web address of its own."""
        return _link_urls(links)

    @field_validator("origin")
    @classmethod
    def _origin(cls, origin: str | None) -> str | None:
        return None if origin is None else web_origin(origin, what="the portal")

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, aliases: dict[str, Place]) -> dict[str, Place]:
        """Each alias by its portal origin as a browser compares it, which is how the UIs look."""
        if len(aliases) > ALIASES:
            raise ValueError(f"{len(aliases)} aliases: at most {ALIASES}")
        named: dict[str, Place] = {}
        for portal, place in aliases.items():
            origin = web_origin(portal, what="the portal")
            if origin in named:
                raise ValueError(f"the portal at {origin} is aliased twice")
            named[origin] = place
        return named

    @model_validator(mode="after")
    def _aliased_origin(self) -> "Site":
        """Refuse aliases without the portal's own origin, which the UIs tell them apart from."""
        if self.aliases and self.origin is None:
            raise ValueError("aliases are other origins of the portal: name its own origin too")
        if self.origin in self.aliases:
            raise ValueError(f"{self.origin} is the portal's own origin, not an alias of it")
        return self

    @model_validator(mode="after")
    def _editors_apart(self) -> "Site":
        """Refuse mini apps, an editor or a link on a portal's origin, or on apps' or Supabase's.

        The portal frames mini apps and editors with their origin's scripts allowed, so each must
        be an origin of its own; a connected app is a site of its own, never the portal's. The
        portal's origins are known here only where ``origin`` and the aliases name them; the UIs
        refuse an editor on their own origin in any case.
        """
        portals = {self.origin, *self.aliases} - {None}
        places = [(self.apps, self.editors, self.links)]
        places += [(p.apps, p.editors, p.links) for p in self.aliases.values()]
        for apps, editors, links in places:
            if apps in portals:
                raise ValueError(f"mini apps at {apps} would share a portal's origin")
            named = (apps, self.supabase_url)
            others = portals | ({_origin_of(url) for url in named if url} - {None})
            named_urls = {f"{key}'s editor": url for key, url in editors.items()} | links
            for what, url in named_urls.items():
                if _origin_of(url) in others:
                    raise ValueError(f"{what} is at {url}: give it an origin of its own")
        return self

    @field_validator("supabase_key")
    @classmethod
    def _publishable(cls, key: str) -> str:
        """Refuse a secret key: ``config.json`` is public; a secret key bypasses row security."""
        if key.startswith("sb_secret_") or _role(key) == "service_role":
            raise ValueError("this is a secret key; config.json takes the publishable one")
        return key


def beside(
    portal: str,
    extra: str,
    *,
    apps: str | None,
    editors: dict[str, str],
    links: dict[str, str] | None = None,
) -> Place:
    """Where mini apps, the editors and the links are for the portal reached at `extra`.

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
        links: The canonical connected apps' addresses, each with its port, such as
            ``http://127.0.0.1:8090/``; none if omitted.

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
        links={key: moved(url, key) for key, url in _link_urls(links or {}).items()},
    )


def _apps_origin(apps: str | None) -> str | None:
    """Mini apps' origin as a browser compares it, or a refusal naming them."""
    return None if apps is None else web_origin(apps, what="mini apps")


def _editor_urls(editors: dict[str, str]) -> dict[str, str]:
    """Each editor's URL on its web origin as a browser compares it, its path kept.

    Raises:
        ValueError: If a key is no native file's app, or a URL has no web origin, or a query or
            fragment.
    """
    for key in editors:
        if not (key.startswith("files:") and KEY.fullmatch(key)):
            raise ValueError(f"{key} is no native file's app: its key is files:<app>")
    return _urls(editors, "'s editor")


def _link_urls(links: dict[str, str]) -> dict[str, str]:
    """Each connected app's URL on its web origin as a browser compares it, its path kept.

    Raises:
        ValueError: If a key isn't a valid integration key, or a URL has no web origin, or a
            query or fragment.
    """
    return _urls(links, "")


def _urls(urls: dict[str, str], whose: str) -> dict[str, str]:
    """Each URL on its web origin as a browser compares it, its path kept: an editor's or a link's.

    Raises:
        ValueError: If a key isn't an integration's, or a URL has no web origin, or a query or
            fragment, or a path with an empty, ``.`` or ``..`` segment.
    """
    kept: dict[str, str] = {}
    for key, url in urls.items():
        if not KEY.fullmatch(key):
            raise ValueError(f"{key} isn't a valid integration key: a name or family:name")
        what = f"{key}{whose}"
        parts = urlsplit(url)
        if parts.query or parts.fragment:
            raise ValueError(f"{what} is at {url}: no query or fragment")
        # The URL may have a path; its origin is what must be a web origin.
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        at = web_origin(origin, what=what)
        if not EDITOR_PATH.fullmatch(parts.path):
            raise ValueError(
                f"{what} is at {url}: a path of letters, digits and ._~-/, "
                "no empty, . or .. segment"
            )
        kept[key] = at + parts.path
    return kept


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
