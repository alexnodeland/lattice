"""The first filter on a mini app's HTML: it names nothing to load (lattice RFC-0005).

Private to artifactr.ui: the agent's tools and the checks refuse an app's HTML it finds wanting,
as each writes one. An app reaches no network, and the policy it runs under is what holds that
(ADR-0082); this filter only tells a model at once that it wrote a script, a module, a stylesheet,
an image, a font or a frame to load from somewhere, so it writes it inline, or as a ``data:`` URL,
instead. It reads the markup with the standard library's tokenizer, as a browser's reads it, the
CSS of ``style`` elements and attributes, a frame's ``srcdoc``, and a script's static imports and
import map; it doesn't run scripts, so what one builds at run time is the policy's alone.
"""

import json
import re
from collections.abc import Iterator
from html.parser import HTMLParser
from typing import Final, cast, override

URL_ATTRIBUTES: Final = frozenset(
    {
        "action",
        "background",
        "data",
        "formaction",
        "href",
        "icon",
        "manifest",
        "poster",
        "src",
        "xlink:href",
    }
)
"""The attributes whose value is one URL that the browser may load or go to."""

URL_LISTS: Final = frozenset({"imagesrcset", "ping", "srcset"})
"""The attributes whose value lists URLs, between descriptors such as ``2x``."""

LOCAL: Final = ("#", "data:", "javascript:", "mailto:", "tel:", "about:blank")
"""What a URL may start with, as written, ignoring case: none of these loads from anywhere."""

_CSS_URL: Final = re.compile(
    r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)|@import\s*(?:"([^"]*)"|'([^']*)')""",
    re.IGNORECASE,
)
_IMAGE_SET: Final = re.compile(r"image-set\(([^)]*)\)", re.IGNORECASE)
_QUOTED: Final = re.compile(r""""([^"]*)"|'([^']*)'""")
_IMPORT: Final = re.compile(
    r"""(?:\bfrom|\bimport\s*\(?)\s*["']((?:[a-z][a-z0-9+.-]*:)?//[^"']*)["']""", re.IGNORECASE
)


def refused(html: str) -> str | None:
    """Say why an app's HTML is refused, naming what it would load and where; or None."""
    if found := loaded(html):
        return (
            "the HTML loads from outside the app, which reaches no network: write what it needs "
            f"inline, or as a data: URL, and open links with ui/open-link ({'; '.join(found)})"
        )
    return None


def loaded(html: str) -> list[str]:
    """Return what an app's HTML would load or go to, each said where it is, in order."""
    reader = _Reader()
    reader.feed(html)
    reader.close()
    return reader.found


def _local(url: str) -> bool:
    written = url.strip().lower()
    return not written or written.startswith(LOCAL)


def _candidates(srcset: str) -> Iterator[str]:
    """The URLs of a list such as ``srcset``, as a browser splits it.

    Each URL runs up to whitespace, and its descriptors up to the next comma, so a ``data:``
    URL's own comma is kept.
    """
    at = 0
    while at < len(srcset):
        while at < len(srcset) and (srcset[at].isspace() or srcset[at] == ","):
            at += 1
        start = at
        while at < len(srcset) and not srcset[at].isspace():
            at += 1
        url = srcset[start:at]
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            comma = srcset.find(",", at)
            at = len(srcset) if comma < 0 else comma
        if url:
            yield url


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self._in: tuple[str, str | None] | None = None

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        kind = dict(attrs).get("type")
        self._in = (tag, kind) if tag in ("style", "script") else None
        for name, value in attrs:
            if value is None:
                continue
            where = f"<{tag} {name}>"
            if name in URL_ATTRIBUTES:
                self._url(value, where)
            elif name in URL_LISTS:
                for url in _candidates(value):
                    self._url(url, where)
            elif name == "style":
                self._css(value, where)
            elif name == "srcdoc":
                self.found.extend(f"{where}: {each}" for each in loaded(value))
            elif tag == "meta" and name == "http-equiv" and value.strip().lower() == "refresh":
                self.found.append(f"{where}: a refresh, which goes to another page")

    @override
    def handle_endtag(self, tag: str) -> None:
        self._in = None

    @override
    def handle_data(self, data: str) -> None:
        match self._in:
            case ("style", _):
                self._css(data, "<style>")
            case ("script", "importmap"):
                self._import_map(data)
            case ("script", _):
                for found in _IMPORT.finditer(data):
                    self._url(found.group(1), "<script> import")
            case _:
                pass

    def _css(self, css: str, where: str) -> None:
        for found in _CSS_URL.finditer(css):
            self._url(next(group for group in found.groups() if group is not None), where)
        for images in _IMAGE_SET.finditer(css):
            for quoted in _QUOTED.finditer(images.group(1)):
                self._url(quoted.group(1) or quoted.group(2) or "", where)

    def _import_map(self, text: str) -> None:
        try:
            imports = json.loads(text)
        except ValueError:
            return  # not a map the browser takes either
        for url in _strings(imports):
            self._url(url, "<script type=importmap>")

    def _url(self, url: str, where: str) -> None:
        if not _local(url):
            self.found.append(f"{where}: {url.strip()}")


def _strings(value: object) -> Iterator[str]:
    """Every string among an import map's values, however deep."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for each in cast("dict[str, object]", value).values():
            yield from _strings(each)
