"""Web origins an application is told, checked and written as a browser compares them.

A portal, its mini apps' sandbox and each native file's editor are origins of their own, named in
settings and written into Content-Security-Policy headers, ``postMessage`` targets and the
browser's ``event.origin`` checks. A browser compares origins by scheme, host and port, case
aside, with a scheme's default port left out, and ``location.origin`` has that form: so an origin
is kept here as ``scheme://host[:port]``, in lower case, with no default port, and anything that
isn't an origin is refused: a path, a query, a fragment, a user or password, a wildcard, a percent
sign, and plain http anywhere but loopback (``localhost``, ``127.0.0.1`` and ``::1``), where a
test or a developer runs.
"""

import ipaddress
import re
from collections.abc import Sequence
from typing import Final
from urllib.parse import urlsplit

__all__ = ["LOOPBACK", "origins", "web_origin", "web_origins"]

LOOPBACK: Final = frozenset({"localhost", "127.0.0.1", "::1"})
"""The hosts plain http is allowed on: this machine's own."""

DEFAULT_PORTS: Final = {"http": 80, "https": 443}

EXAMPLE: Final = "https://portal.example"

HOST: Final = re.compile(r"[A-Za-z0-9:.\-\[\]]+")
"""The characters an origin's host and port are written in: none a policy or a header separates
on, no space, quote, comma or semicolon, and ASCII alone, so an internationalised name comes as
its punycode."""

LABEL: Final = re.compile(r"(?!-)[a-z0-9-]{1,63}(?<!-)")
"""One label of a host name, as DNS spells it."""


def web_origin(url: str, *, what: str = "the origin") -> str:
    """`url` as the origin a browser sees it as, or a refusal naming `what` it was given for.

    Args:
        url: An origin, such as ``https://portal.example`` or ``http://127.0.0.1:8800``; a
            trailing ``/`` is allowed, as a URL of the origin's root.
        what: What the origin is for, which the refusal names: ``"the portal"``,
            ``"mini apps"``, ``"files:gridcraft's editor"``.

    Returns:
        ``scheme://host[:port]``: the scheme and host in lower case, a bracketed IPv6 host as
        given, and the port only where it isn't the scheme's default.

    Raises:
        ValueError: If `url` is no web origin: no https, or http off loopback; a user or a
            password, or no host; a character in the host or port outside ASCII letters, digits
            and ``.-:[]``, or a host name that isn't DNS labels; a path, query or fragment; a
            ``*`` or a ``%`` anywhere; or an IP address that isn't loopback, which no
            certificate names.
    """
    said = f"{what} is an origin, such as {EXAMPLE}, not {url!r}"
    if "*" in url or "%" in url:
        raise ValueError(f"{said}: no wildcard or escape")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if parts.username is not None or parts.password is not None or not host:
        raise ValueError(f"{said}: a host, with no user or password")
    if not HOST.fullmatch(parts.netloc):
        raise ValueError(f"{said}: ASCII letters, digits and . - : [ ] alone, a name in punycode")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(f"{said}: no path, query or fragment")
    try:
        port = parts.port
    except ValueError as error:
        raise ValueError(f"{said}: {error}") from error
    address = _address(host)
    if address is None and not all(LABEL.fullmatch(each) for each in host.split(".")):
        raise ValueError(f"{said}: a host name of DNS labels")
    loopback = host in LOOPBACK
    if address is not None and not loopback:
        raise ValueError(f"{said}: an IP address that isn't loopback names no certificate")
    if scheme != "https" and not (scheme == "http" and loopback):
        raise ValueError(f"{said}: give it https, or http on loopback")
    if isinstance(address, ipaddress.IPv6Address):
        host = f"[{host}]"
    suffix = "" if port is None or port == DEFAULT_PORTS[scheme] else f":{port}"
    return f"{scheme}://{host}{suffix}"


def web_origins(named: str | Sequence[str], *, what: str = "the origin") -> tuple[str, ...]:
    """One origin or several, each as :func:`web_origin` keeps it, once, in the order named.

    For a setting that took one origin and now takes several (portalr ADR-0084): a string is
    that one origin, and a sequence each of them.

    Raises:
        ValueError: If none is named, or one isn't a web origin.
    """
    given = (named,) if isinstance(named, str) else tuple(named)
    if not given:
        raise ValueError(f"{what} is an origin, such as {EXAMPLE}: name one")
    return tuple(dict.fromkeys(web_origin(each, what=what) for each in given))


def origins(
    csv: str, *, what: str = "the origins", canonical: str | None = None, limit: int = 8
) -> tuple[str, ...]:
    """The origins a comma-separated setting names, each checked, once, and never `canonical`.

    Args:
        csv: The setting's value: origins separated by commas, with any whitespace round them;
            empty names none.
        what: What the origins are for, which a refusal names.
        canonical: An origin named elsewhere, such as the portal's own, which is left out here
            however it is spelled.
        limit: The most origins the setting may name, past which it is refused: a policy that
            names many origins is a mistake, not a deployment.

    Raises:
        ValueError: If any isn't a web origin, or more than `limit` are named, counted after
            those repeated or canonical are left out.
    """
    named = [web_origin(each.strip(), what=what) for each in csv.split(",") if each.strip()]
    kept = canonical if canonical is None else web_origin(canonical, what=what)
    found = tuple(dict.fromkeys(each for each in named if each != kept))
    if len(found) > limit:
        raise ValueError(f"{what} name {len(found)} origins: at most {limit}")
    return found


def _address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """`host` as an IP address, or None for a name."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None
