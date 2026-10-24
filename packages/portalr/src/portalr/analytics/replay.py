"""Session replay's batches, and the check that nothing in one was left unmasked (portalr ADR-0077).

A person's browser records the layout of the pages they visit and where they click, with rrweb,
once they have said yes to replay as well as to analytics; and with every text and every input
masked, a page's content blocked unless the page allows itself, and every attribute that is not
known to be structural masked or left out before a batch leaves it. The relay checks each batch
again, and it is an allow-list: a key is kept only if rrweb's events have it, an attribute only if
its name is in ``replay_allowlist.json`` and its value fits that name's pattern, and any other
string must be asterisks and spaces. A batch with one that is neither is dropped whole, never
forwarded. The browser's recorder reads the same file, so a wrong pattern is wrong in both: the
check is a second look at what the recorder sent, not a second opinion on what is structural.

**No stylesheet text comes from a browser.** A page's own stylesheet is named by the recorder
(``rr_css``, the file's name), and the relay puts in the text of the file it serves under that
name; any other CSS the page makes is left out. So there is no CSS from a client to read, and none
of its comments, strings and escapes to be fooled by. An inline ``style`` is a short list of
declarations, each a property from a list and values of numbers and keywords from a list.

Every string is capped in length before any pattern is tried (``limits``), and every pattern is
written so that matching it takes time linear in its input; a test holds each to that.
"""

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Final, cast

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MOST_REPLAY_EVENTS: Final = 200
"""The most rrweb events one batch holds: Umami's own limit."""

MOST_REPLAY_BYTES: Final = 512 * 1024
"""The largest batch the relay takes, in bytes: under Umami's own megabyte."""

_LIST: Final[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "replay_allowlist.json").read_text(encoding="utf-8")
)
"""What may be unmasked, which the browser's recorder reads too."""

WORDED: Final = frozenset[str](_LIST["worded"])
"""The keys whose values may carry words, a person's input, or an address."""

_PATTERNS: Final = {name: re.compile(text) for name, text in _LIST["patterns"].items()}
_ATTRIBUTES: Final = cast("dict[str, str]", _LIST["attributes"])
_NAMESPACES: Final = cast("dict[str, list[str]]", _LIST["namespaces"])
_STYLED: Final = frozenset[str](_LIST["styled"])
_CSS_TEXT: Final = frozenset[str](_LIST["css_text"]["keys"])
_CSS_ALLOWED: Final = frozenset[str](_LIST["css_text"]["allowed"])
_KEYS: Final = frozenset[str](_LIST["keys"])
_MARKS: Final = cast("dict[str, list[str]]", _LIST["marks"])
_NAME: Final = re.compile(_LIST["name"])
_DOCTYPE: Final = {key: re.compile(text) for key, text in _LIST["doctype"].items()}
_STRUCTURAL: Final = {key: re.compile(text) for key, text in _LIST["structural_keys"].items()}
_LIMITS: Final = cast("dict[str, int]", _LIST["limits"])
_PROPERTIES: Final = frozenset[str](_LIST["style"]["properties"])
_KEYWORDS: Final = frozenset[str](_LIST["style"]["keywords"])
_OPERATORS: Final = frozenset[str](_LIST["style"]["operators"])
_CUSTOM: Final = re.compile(_LIST["style"]["custom"])
_NUMBER: Final = _PATTERNS["number"]
SCRIPT: Final = cast(str, _LIST["script"])
"""What rrweb puts in place of a script's text: never what the page ran."""

_MASKED: Final = re.compile(r"[\s*]*")


class ReplayBatch(BaseModel):
    """A browser's replay events, in the session portalr signed for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: Annotated[str, StringConstraints(max_length=128)]
    events: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=MOST_REPLAY_EVENTS)]


def masked(value: str) -> bool:
    """Whether a value is masked: asterisks and spaces alone, or nothing."""
    return _MASKED.fullmatch(value) is not None


def _short(name: str, value: str) -> bool:
    """Whether a string is within the list's length for `name`, checked before any pattern."""
    return len(value) <= _LIMITS.get(name, _LIMITS["default"])


def _token_ok(token: str) -> bool:
    """Whether a word of an inline style's value is a number, a keyword or an operator."""
    return token in _KEYWORDS or token in _OPERATORS or _NUMBER.fullmatch(token) is not None


def _declarations_ok(text: str) -> bool:
    """Whether an inline style is a short list of declarations that can render no word.

    Each has a property from the list (or a custom property's name) and a value of numbers with
    units and keywords from the list, and the few characters between them: no string, no
    ``url()``, no ``var()``, no escape, no comment.
    """
    if not _short("style", text) or not text.isascii():
        return False
    for declaration in text.split(";"):
        prop, colon, value = declaration.partition(":")
        if not declaration.strip():
            continue
        prop = prop.strip().lower()
        if not colon or (prop not in _PROPERTIES and _CUSTOM.fullmatch(prop) is None):
            return False
        words = value.replace("(", " ").replace(")", " ").replace(",", " ").split()
        if not all(_token_ok(word.lower()) for word in words):
            return False
    return True


def _style_ok(value: dict[str, Any]) -> bool:
    """Whether the changes to an element's inline style, rrweb's diff of it, render no word."""
    for prop, change in value.items():
        if change is None or change is False:
            continue
        shown: Any = change
        if isinstance(change, list):
            pair = cast("list[Any]", change)
            if len(pair) != 2 or pair[1] not in ("", "important"):
                return False
            shown = pair[0]
        if not (isinstance(shown, str) and _short("style", shown)):
            return False
        if not _declarations_ok(f"{prop}:{shown}"):
            return False
    return True


def _named(name: str) -> bool:
    """Whether an attribute's name is on the list, or a `data-*` or `aria-*` name."""
    return (
        name in _ATTRIBUTES
        or name in WORDED
        or name in _MARKS
        or name in _NAMESPACES
        or name in _STYLED
        or name.startswith(("data-", "aria-"))
    )


def _attribute_ok(name: str, value: Any) -> bool:
    """Whether an attribute of an element may be sent as it is."""
    if _NAME.fullmatch(name) is None or not _named(name):
        return False
    if name in _MARKS:
        return value in _MARKS[name]
    if isinstance(value, dict):
        return name in _STYLED and _style_ok(cast("dict[str, Any]", value))
    if isinstance(value, list):
        return False
    if value is None:
        return True
    if not isinstance(value, str):
        return name in _ATTRIBUTES
    if masked(value):
        return True
    if not _short(name, value):
        return False
    if name in _STYLED:
        return _declarations_ok(value)
    if name in _NAMESPACES:
        return value in _NAMESPACES[name]
    kinds = _ATTRIBUTES.get(name)
    return kinds is not None and any(
        _PATTERNS[kind].fullmatch(value) is not None for kind in kinds.split("|")
    )


def _doctype(node: dict[str, Any]) -> bool:
    """Whether a node is rrweb's document type, and its three strings are plain."""
    return (
        node.get("type") == 1
        and "publicId" in node
        and "systemId" in node
        and all(
            isinstance(node.get(key), str)
            and _short(key, node[key])
            and pattern.fullmatch(node[key]) is not None
            for key, pattern in _DOCTYPE.items()
            if key in node
        )
    )


def _string_ok(node: dict[str, Any], key: str, value: str) -> bool:
    """Whether a string under `key` of a node, not an attribute, may be sent as it is."""
    if masked(value):
        return True
    if not _short(key, value):
        return False
    if key == "textContent":
        return value == SCRIPT
    if key in _CSS_TEXT:
        return value in _CSS_ALLOWED
    if key == "value" and isinstance(node.get("property"), str):
        # A change to a style declaration: its property, and the value it is given.
        return _declarations_ok(f"{node['property']}:{value}")
    if key == "property":
        return (value.isascii() and value.lower() in _PROPERTIES) or _CUSTOM.fullmatch(
            value.lower()
        ) is not None
    if key in _DOCTYPE and node.get("type") == 1:
        return _doctype(node)
    if key in _STRUCTURAL:
        return _STRUCTURAL[key].fullmatch(value) is not None
    return False


def unmasked(events: list[dict[str, Any]]) -> str | None:
    """The first key whose value is neither masked nor known to be structural, or None.

    A key of a node is one rrweb's events have; a string under any key but those the allow-list
    names must be masked; an attribute is kept only by name and pattern; a worded key holds a
    string or nothing; and a string in a list must be masked.
    """
    stack: list[tuple[Any, bool]] = [(event, False) for event in events]
    while stack:
        item, attributes = stack.pop()
        if isinstance(item, list):
            for each in cast("list[Any]", item):
                if isinstance(each, str) and not masked(each):
                    return "list"
                stack.append((each, False))
            continue
        if not isinstance(item, dict):
            continue
        node = cast("dict[str, Any]", item)
        for key, value in node.items():
            if attributes:
                if not _attribute_ok(key, value):
                    return key
                continue
            if key not in _KEYS:
                return key
            if key in WORDED and not (value is None or isinstance(value, str)):
                return key
            if isinstance(value, str):
                if not _string_ok(node, key, value):
                    return key
            elif isinstance(value, dict | list):
                stack.append((cast(Any, value), key == "attributes" and isinstance(value, dict)))
    return None


MOST_SHEETS: Final = 8
"""The most stylesheets one batch may name: a page has a few, and each is the file's whole text."""

MOST_EXPANDED: Final = 1024 * 1024
"""The most bytes the stylesheets a batch names may add to it: under Umami's own megabyte."""

NOTHING: Final = "x{}"
"""A rule that does nothing: what stands for CSS that is not sent, or a stylesheet not served."""


def _named_sheets(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The attribute maps in the events that name a stylesheet (``rr_css``)."""
    maps: list[dict[str, Any]] = []
    stack: list[Any] = list(events)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(cast("list[Any]", item))
        elif isinstance(item, dict):
            node = cast("dict[str, Any]", item)
            attributes = node.get("attributes")
            if isinstance(attributes, dict) and "rr_css" in attributes:
                maps.append(cast("dict[str, Any]", attributes))
            stack.extend(node.values())
    return maps


def expansion(events: list[dict[str, Any]], sheets: Mapping[str, str]) -> tuple[int, int]:
    """How many stylesheets the events name, and how many bytes their text would add."""
    maps = _named_sheets(events)
    return len(maps), sum(len(sheets.get(each["rr_css"], NOTHING).encode()) for each in maps)


def inlined(events: list[dict[str, Any]], sheets: Mapping[str, str]) -> bool:
    """Put in the text of each stylesheet the recorder named, from the files the app serves.

    The recorder names a page's own stylesheet by its file (``rr_css``) and sends none of its text.
    The text here is the file's, so what is forwarded to Umami for a styled replay is the
    application's. A name the app doesn't serve (a tab from before a deploy) gets a rule that does
    nothing, and the rest of the batch goes on. Returns False, with the events as they were, if the
    batch names more than ``MOST_SHEETS`` or the texts would add more than ``MOST_EXPANDED``
    bytes: a name is a few bytes, and a file's text is not.
    """
    uses, added = expansion(events, sheets)
    if uses > MOST_SHEETS or added > MOST_EXPANDED:
        return False
    for each in _named_sheets(events):
        each["_cssText"] = sheets.get(each.pop("rr_css"), NOTHING)
    return True
