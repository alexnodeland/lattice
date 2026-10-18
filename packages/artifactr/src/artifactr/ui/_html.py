"""The first filter on a mini app's HTML: it names nothing to load (lattice RFC-0005).

Private to artifactr.ui: :class:`~artifactr.ui.types.App` refuses HTML it finds wanting. An app
reaches no network, and the policy it runs under is what holds that (ADR-0082); this filter only
tells a model at once that it wrote a script, a stylesheet, an image, a font or a frame to load
from somewhere, so it writes it inline, or as a ``data:`` URL, instead. It reads the markup with
the standard library's tokenizer, as a browser's reads it, and the CSS of ``style`` elements and
attributes; it doesn't read scripts, which only the policy holds.
"""

import re
from html.parser import HTMLParser
from typing import Final, override

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

LOCAL: Final = ("#", "data:", "javascript:", "about:blank")
"""What a URL may start with, as written, ignoring case: nothing of these leaves the frame."""

_DESCRIPTOR: Final = re.compile(r"^\d+(?:\.\d+)?[wxh],?$", re.IGNORECASE)
_CSS_URL: Final = re.compile(
    r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)"""
    r"""|@import\s*(?:"([^"]*)"|'([^']*)')"""
    r"""|image-set\(\s*(?:"([^"]*)"|'([^']*)')""",
    re.IGNORECASE,
)


def loaded(html: str) -> list[str]:
    """Return what an app's HTML would load or go to, each said where it is, in order."""
    reader = _Reader()
    reader.feed(html)
    reader.close()
    return reader.found


def _local(url: str) -> bool:
    written = url.strip().lower()
    return not written or written.startswith(LOCAL)


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self._style = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._style = tag == "style"
        for name, value in attrs:
            where = f"<{tag} {name}>"
            if value is None:
                continue
            if name in URL_ATTRIBUTES:
                self._url(value, where)
            elif name in URL_LISTS:
                for token in value.split():
                    if not _DESCRIPTOR.match(token):
                        self._url(token.strip(","), where)
            elif name == "style":
                self._css(value, where)
            elif tag == "meta" and name == "http-equiv" and value.strip().lower() == "refresh":
                self.found.append(f"{where}: a refresh, which goes to another page")

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._style = False

    @override
    def handle_data(self, data: str) -> None:
        if self._style:
            self._css(data, "<style>")

    def _css(self, css: str, where: str) -> None:
        for match in _CSS_URL.finditer(css):
            self._url(next(group for group in match.groups() if group is not None), where)

    def _url(self, url: str, where: str) -> None:
        if not _local(url):
            self.found.append(f"{where}: {url.strip()}")
