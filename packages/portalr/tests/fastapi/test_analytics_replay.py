"""Session replay: its own yes, after analytics', masked as it is sent, and checked as it comes."""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from grantr.grants import Grants
from portalr.analytics import InMemoryConsent, InMemoryRateLimiter, Relay
from portalr.analytics.relay import MOST_COPIES
from portalr.analytics.replay import (
    _LIST,
    MOST_EXPANDED,
    MOST_REPLAY_BYTES,
    MOST_SHEETS,
    ReplayBatch,
    _declarations_ok,
    expansion,
    inlined,
    masked,
    unmasked,
)
from portalr.fastapi.openapi import openapi_document
from portalr.invites import Invite
from portalr.readers import Analytics, Readers

from .conftest import app_for
from .test_analytics_umami import ACME, GLOBEX, KEY, ME, WEBSITE, Stand, umami_of

ALICE = {"x-user": "alice", "x-tenant": "acme"}

# As rrweb records a page, masked: a full snapshot, a text mutation and an input.
SNAPSHOT = {
    "type": 2,
    "data": {
        "node": {
            "type": 0,
            "childNodes": [
                {
                    "type": 2,
                    "tagName": "style",
                    "attributes": {},
                    "childNodes": [
                        {"type": 3, "textContent": "", "isStyle": True},
                    ],
                },
                {
                    "type": 2,
                    "tagName": "script",
                    "childNodes": [
                        {"type": 3, "textContent": "SCRIPT_PLACEHOLDER"},
                    ],
                },
                {
                    "type": 2,
                    "tagName": "button",
                    "attributes": {
                        "class": "btn",
                        "aria-label": "****",
                        "data-portalr-replay": "block",
                    },
                    "childNodes": [{"type": 3, "textContent": "***** **"}],
                },
                {"type": 2, "tagName": "input", "attributes": {"value": "*****", "type": "text"}},
            ],
        }
    },
}
MUTATION = {"type": 3, "data": {"source": 0, "texts": [{"id": 4, "value": "***"}]}}
INPUT = {"type": 3, "data": {"source": 5, "id": 9, "text": "*******", "isChecked": False}}


DOCTYPE = {"type": 1, "name": "html", "publicId": "", "systemId": ""}


def test_a_masked_recording_passes() -> None:
    assert unmasked([SNAPSHOT, MUTATION, INPUT]) is None
    assert unmasked([DOCTYPE]) is None, (
        "a document type's name is the document's, and a mask in its place breaks a player"
    )
    assert unmasked([{**DOCTYPE, "name": "Launch on Tuesday"}]) == "name"
    assert unmasked([{"type": 1, "name": "html"}]) == "name", "only a document type's shape"
    assert unmasked([{"type": 2, "name": "html", "publicId": "", "systemId": ""}]) == "name"
    assert unmasked([{"data": [1, "***", None, ["* *"], True]}]) is None, "a list holds numbers"
    assert unmasked([{"data": [1, "plain"]}]) == "list", "and a string in one must be masked"
    assert unmasked([{"data": [["x"]]}]) == "list"
    assert masked("")
    assert masked("* **")
    assert not masked("a")


@pytest.mark.parametrize(
    ("event", "key"),
    [
        ({"type": 3, "textContent": "Launch on Tuesday"}, "textContent"),
        ({"attributes": {"value": "hunter2"}}, "value"),
        ({"data": {"texts": [{"id": 1, "value": "said"}]}}, "value"),
        ({"data": {"source": 5, "text": "typed"}}, "text"),
        ({"attributes": {"aria-label": "Open thread: Q3 plans"}}, "aria-label"),
        ({"attributes": {"title": "alice@acme.com"}}, "title"),
        ({"attributes": {"href": "/t/acme/w/notes/threads/thr_1"}}, "href"),
        ({"attributes": {"src": "https://avatars/alice.png"}}, "src"),
        ({"attributes": {"data-name": "Q3 plans"}}, "data-name"),
        ({"type": 3, "textContent": "body { content: 'x' }"}, "textContent"),
        # Off the list: a name the allow-list doesn't know, however plain its value.
        ({"attributes": {"custom-attr": "walrus"}}, "custom-attr"),
        ({"attributes": {"onclick": "go"}}, "onclick"),
        ({"attributes": {"action": "javascript:go()"}}, "action"),
        ({"attributes": {"aria-roledescription": "walrus"}}, "aria-roledescription"),
        ({"attributes": {"class": 'a "walrus" b'}}, "class"),
        ({"attributes": {"id": "alice@acme.test"}}, "id"),
        ({"attributes": {"role": "a word"}}, "role"),
        ({"attributes": {"xmlns": "http://x.test/ns"}}, "xmlns"),
        ({"attributes": {"data-portalr-replay": "walrus"}}, "data-portalr-replay"),
        ({"attributes": {"data-portalr-replay": ""}}, "data-portalr-replay"),
        ({"attributes": {"data-portalr-replay": "****"}}, "data-portalr-replay"),
        ({"attributes": {"style": "content: 'walrus someone said'"}}, "style"),
        ({"attributes": {"style": {"content": "attr(data-name)"}}}, "style"),
        ({"attributes": {"value": 12345}}, "value"),
        ({"attributes": {"placeholder": ["walrus"]}}, "placeholder"),
        ({"attributes": {"title": {"a": "b"}}}, "title"),
        ({"attributes": {"class": ["walrus"]}}, "class"),
        ({"type": 1, "name": "html", "publicId": "walrus", "systemId": ""}, "name"),
        ({"type": 1, "name": "html", "publicId": "", "systemId": "http://x.test/walrus"}, "name"),
        ({"type": 3, "textContent": "walrus", "isStyle": True}, "textContent"),
        ({"type": 3, "textContent": "a{}", "isStyle": False}, "textContent"),
        ({"type": 2, "tagName": "div x"}, "tagName"),
        ({"type": 5, "data": {"payload": "walrus"}}, "payload"),
        ({"data": {"value": 4}}, "value"),
    ],
)
def test_any_word_input_or_address_unmasked_is_found(event: dict[str, object], key: str) -> None:
    assert unmasked([SNAPSHOT, event]) == key


def test_the_inline_styles_the_allow_list_vectors_name_are_held_to() -> None:
    vectors = _LIST["vectors"]
    assert all(_declarations_ok(each) for each in vectors["declarations_ok"])
    assert not any(_declarations_ok(each) for each in vectors["declarations_bad"])


# Written apart from the allow-list: every attribute a page may carry, HTML, ARIA, SVG and the
# handlers, as the standards name them. A word stamped into each must reach no accepted batch.
ATTRIBUTES = [
    "accept",
    "accept-charset",
    "accesskey",
    "action",
    "align",
    "allow",
    "allowfullscreen",
    "alt",
    "as",
    "async",
    "autocapitalize",
    "autocomplete",
    "autofocus",
    "autoplay",
    "background",
    "bgcolor",
    "border",
    "capture",
    "challenge",
    "charset",
    "checked",
    "cite",
    "class",
    "color",
    "cols",
    "colspan",
    "content",
    "contenteditable",
    "controls",
    "coords",
    "crossorigin",
    "data",
    "data-name",
    "data-testid",
    "data-x",
    "datetime",
    "decoding",
    "default",
    "defer",
    "dir",
    "dirname",
    "disabled",
    "download",
    "draggable",
    "enctype",
    "enterkeyhint",
    "for",
    "form",
    "formaction",
    "formenctype",
    "formmethod",
    "formnovalidate",
    "formtarget",
    "headers",
    "height",
    "hidden",
    "high",
    "href",
    "hreflang",
    "http-equiv",
    "id",
    "imagesizes",
    "imagesrcset",
    "inert",
    "inputmode",
    "integrity",
    "is",
    "ismap",
    "itemid",
    "itemprop",
    "itemref",
    "itemscope",
    "itemtype",
    "kind",
    "label",
    "lang",
    "list",
    "loading",
    "loop",
    "low",
    "manifest",
    "max",
    "maxlength",
    "media",
    "method",
    "min",
    "minlength",
    "multiple",
    "muted",
    "name",
    "nomodule",
    "nonce",
    "novalidate",
    "open",
    "optimum",
    "pattern",
    "ping",
    "placeholder",
    "playsinline",
    "poster",
    "preload",
    "radiogroup",
    "readonly",
    "referrerpolicy",
    "rel",
    "required",
    "rev",
    "reversed",
    "role",
    "rows",
    "rowspan",
    "sandbox",
    "scope",
    "scoped",
    "selected",
    "shape",
    "size",
    "sizes",
    "slot",
    "span",
    "spellcheck",
    "src",
    "srcdoc",
    "srclang",
    "srcset",
    "start",
    "step",
    "style",
    "summary",
    "tabindex",
    "target",
    "title",
    "translate",
    "type",
    "usemap",
    "value",
    "width",
    "wrap",
    "onclick",
    "onerror",
    "onload",
    "onmouseover",
    "oninput",
    "onchange",
    "onfocus",
    "onsubmit",
    "aria-activedescendant",
    "aria-atomic",
    "aria-autocomplete",
    "aria-braillelabel",
    "aria-brailleroledescription",
    "aria-busy",
    "aria-checked",
    "aria-colcount",
    "aria-colindex",
    "aria-colspan",
    "aria-controls",
    "aria-current",
    "aria-describedby",
    "aria-description",
    "aria-details",
    "aria-disabled",
    "aria-dropeffect",
    "aria-errormessage",
    "aria-expanded",
    "aria-flowto",
    "aria-grabbed",
    "aria-haspopup",
    "aria-hidden",
    "aria-invalid",
    "aria-keyshortcuts",
    "aria-label",
    "aria-labelledby",
    "aria-level",
    "aria-live",
    "aria-modal",
    "aria-multiline",
    "aria-multiselectable",
    "aria-orientation",
    "aria-owns",
    "aria-placeholder",
    "aria-posinset",
    "aria-pressed",
    "aria-readonly",
    "aria-relevant",
    "aria-required",
    "aria-roledescription",
    "aria-rowcount",
    "aria-rowindex",
    "aria-rowspan",
    "aria-selected",
    "aria-setsize",
    "aria-sort",
    "aria-valuemax",
    "aria-valuemin",
    "aria-valuenow",
    "aria-valuetext",
    "accent-height",
    "alignment-baseline",
    "clip-path",
    "clip-rule",
    "cx",
    "cy",
    "d",
    "direction",
    "dominant-baseline",
    "dx",
    "dy",
    "fill",
    "fill-opacity",
    "fill-rule",
    "filter",
    "flood-color",
    "font-family",
    "font-size",
    "font-weight",
    "fx",
    "fy",
    "gradientTransform",
    "gradientUnits",
    "href",
    "image-rendering",
    "lengthAdjust",
    "letter-spacing",
    "marker-end",
    "marker-mid",
    "marker-start",
    "mask",
    "offset",
    "opacity",
    "orient",
    "overflow",
    "paint-order",
    "pathLength",
    "patternUnits",
    "points",
    "preserveAspectRatio",
    "r",
    "refX",
    "refY",
    "rx",
    "ry",
    "spreadMethod",
    "startOffset",
    "stop-color",
    "stop-opacity",
    "stroke",
    "stroke-dasharray",
    "stroke-dashoffset",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-opacity",
    "stroke-width",
    "text-anchor",
    "text-decoration",
    "textLength",
    "transform",
    "vector-effect",
    "version",
    "viewBox",
    "visibility",
    "word-spacing",
    "writing-mode",
    "x",
    "x1",
    "x2",
    "xlink:actuate",
    "xlink:arcrole",
    "xlink:href",
    "xlink:role",
    "xlink:show",
    "xlink:title",
    "xlink:type",
    "xml:lang",
    "xml:space",
    "xmlns",
    "xmlns:xlink",
    "y",
    "y1",
    "y2",
    "z",
    "_cssText",
    "rr_dataURL",
    "rr_mediaState",
    "rr_scrollLeft",
    "rr_scrollTop",
    "rr_width",
    "rr_height",
]

SENTINEL = 'Zq7 "walrus" said @alice'


# What takes a bare word, written apart from the allow-list, from what each attribute is: the
# names of things the page's code gives (an id, a class, a role, a relation) and the enumerations
# (a state, a boolean, a kind of line end, a colour keyword). Nothing else takes a plain word.
TAKES_A_WORD = frozenset(
    [
        "async",
        "autofocus",
        "autoplay",
        "controls",
        "crossorigin",
        "decoding",
        "default",
        "defer",
        "enterkeyhint",
        "formnovalidate",
        "inert",
        "ismap",
        "loading",
        "loop",
        "muted",
        "nomodule",
        "novalidate",
        "playsinline",
        "popover",
        "preload",
        "reversed",
        "scope",
        "spellcheck",
        "translate",
        "wrap",
        "fetchpriority",
        "class",
        "id",
        "role",
        "type",
        "lang",
        "dir",
        "target",
        "for",
        "form",
        "headers",
        "inputmode",
        "disabled",
        "checked",
        "hidden",
        "open",
        "readonly",
        "required",
        "multiple",
        "selected",
        "draggable",
        "contenteditable",
        "focusable",
        "stroke-linecap",
        "stroke-linejoin",
        "fill-rule",
        "clip-rule",
        "aria-expanded",
        "aria-hidden",
        "aria-checked",
        "aria-selected",
        "aria-pressed",
        "aria-disabled",
        "aria-current",
        "aria-haspopup",
        "aria-live",
        "aria-busy",
        "aria-modal",
        "aria-orientation",
        "aria-sort",
        "aria-atomic",
        "aria-multiselectable",
        "aria-required",
        "aria-readonly",
        "aria-invalid",
        "aria-autocomplete",
        "aria-labelledby",
        "aria-describedby",
        "aria-controls",
        "aria-owns",
        "aria-activedescendant",
    ]
)


def test_a_word_stamped_into_any_attribute_a_page_may_carry_reaches_no_accepted_batch() -> None:
    for name in set(ATTRIBUTES):
        events = [{"type": 2, "tagName": "div", "attributes": {name: SENTINEL}, "childNodes": []}]
        assert unmasked(events) is not None or "walrus" not in json.dumps(events), name
        assert unmasked(events) is not None, f"{name} takes a quoted sentence"
    accepted = {
        name
        for name in set(ATTRIBUTES)
        if unmasked([{"type": 2, "tagName": "div", "attributes": {name: "walrus"}}]) is None
    }
    assert accepted == TAKES_A_WORD & set(ATTRIBUTES), (
        "exactly the attributes that name or enumerate things take a bare word: "
        f"{sorted(accepted ^ (TAKES_A_WORD & set(ATTRIBUTES)))}"
    )
    assert not TAKES_A_WORD - set(_LIST["attributes"]), "and each of them is on the list"


@pytest.mark.parametrize(
    ("attributes", "key"),
    [
        ({"id": "Alice Smith"}, "id"),
        ({"id": "alice smith's plan"}, "id"),
        ({"class": "user-alice-smith secret@acme"}, "class"),
        ({"class": "a" * 101}, "class"),
        ({"alice-smith": True}, "alice-smith"),
        ({"alice-smith": ""}, "alice-smith"),
        ({"alice-smith": "****"}, "alice-smith"),
        ({"fill": "alice smith"}, "fill"),
        ({"stroke": "alice"}, "stroke"),
        ({"rel": "alice smith"}, "rel"),
        ({"autocomplete": "alice"}, "autocomplete"),
        ({"alice smith": ""}, "alice smith"),
        ({"x" * 65: ""}, "x" * 65),
        ({"hidden-by-alice": 3}, "hidden-by-alice"),
        ({"aria-labelledby": "a b c d e f g h i j"}, "aria-labelledby"),
        ({"for": "Alice Smith"}, "for"),
    ],
)
def test_an_identifier_is_one_and_a_name_is_a_name(attributes: dict[str, object], key: str) -> None:
    assert unmasked([{"type": 2, "attributes": attributes}]) == key


def test_what_the_page_names_and_enumerates_is_kept() -> None:
    kept = {
        "id": "_r_k_",
        "class": "@container flex w-[calc(100%-1rem)] data-[open]:bg-wash",
        "role": "menuitem",
        "aria-labelledby": "base-ui-_r_e_ _r_h_",
        "aria-checked": "true",
        "tabindex": "-1",
        "d": "M10 9H8",
        "xmlns": "http://www.w3.org/2000/svg",
        "data-open": "",
        "data-portalr-replay": "allow",
        "style": "position: fixed; inset: 0px;",
        "checked": True,
        "title": None,
    }
    assert unmasked([{"type": 2, "attributes": kept}]) is None


def _every_regex() -> list[tuple[str, re.Pattern[str]]]:
    """Each pattern the list holds and each the module compiled: none escapes the timing test."""
    from portalr.analytics import replay

    found = [(f"patterns.{name}", re.compile(text)) for name, text in _LIST["patterns"].items()]
    found += [(f"doctype.{key}", re.compile(text)) for key, text in _LIST["doctype"].items()]
    found += [(f"structural.{key}", re.compile(t)) for key, t in _LIST["structural_keys"].items()]
    found += [
        (name, value) for name, value in vars(replay).items() if isinstance(value, re.Pattern)
    ]
    return found


HOSTILE = ["7", "a", " ", "-", ".", "/*", "url(", "x:", "'", '"', "\\", "px", "a b", "\n"]


@pytest.mark.parametrize(("name", "pattern"), _every_regex(), ids=lambda each: str(each)[:40])
def test_every_pattern_is_matched_in_time_linear_in_what_is_matched(
    name: str, pattern: re.Pattern[str]
) -> None:
    started = time.perf_counter()
    for unit in HOSTILE:
        for size in (8_000, 16_000):
            text = (unit * size)[:size] + "!"
            pattern.fullmatch(text)
            pattern.fullmatch("!" + text)
    assert time.perf_counter() - started < 0.5, name


def test_the_checks_cost_no_more_time_for_a_hostile_string_than_a_plain_one() -> None:
    started = time.perf_counter()
    for unit in HOSTILE:
        text = unit * 100_000
        attributes = dict.fromkeys(("width", "style", "class", "d", "id", "title", "rel"), text)
        unmasked([{"type": 2, "tagName": text, "attributes": attributes, "childNodes": []}])
        unmasked(
            [{"type": 3, "textContent": text, "data": {"source": 0, "texts": [{"value": text}]}}]
        )
    assert time.perf_counter() - started < 1.0


def test_a_string_is_capped_before_any_pattern_is_tried() -> None:
    assert unmasked([{"type": 2, "attributes": {"width": "7" * 300}}]) == "width"
    assert unmasked([{"type": 2, "attributes": {"id": "a" * 300}}]) == "id"
    assert unmasked([{"type": 2, "attributes": {"style": "top:0px;" * 300}}]) == "style"
    assert unmasked([{"type": 2, "tagName": "d" * 300}]) == "tagName"
    assert unmasked([{"type": 3, "textContent": "*" * 100_000}]) is None, "a mask is any length"


def test_no_stylesheet_text_comes_from_a_browser_and_a_named_file_is_given_its_text() -> None:
    for key in ("_cssText",):
        assert unmasked([{"type": 2, "attributes": {key: ".a{color:red}"}}]) == key
    assert unmasked([{"type": 3, "textContent": ".a{color:red}", "isStyle": True}]) == "textContent"
    assert unmasked([{"data": {"adds": [{"rule": ".a{color:red}"}]}}]) == "rule"
    assert unmasked([{"data": {"source": 8, "replace": ".a{color:red}"}}]) == "replace"
    assert unmasked([{"data": {"adds": [{"rule": "x{}"}]}}]) is None
    link = [{"type": 2, "attributes": {"rel": "stylesheet", "rr_css": "index-ab12.css"}}]
    assert unmasked(link) is None
    assert inlined(link, {"index-ab12.css": ".a{}"})
    assert link[0]["attributes"] == {"rel": "stylesheet", "_cssText": ".a{}"}
    other = [{"type": 2, "attributes": {"rr_css": "other.css"}}]
    assert inlined(other, {"index-ab12.css": ".a{}"}), (
        "a name not served gets a rule that does nothing"
    )
    assert other[0]["attributes"] == {"_cssText": "x{}"}
    assert unmasked([{"type": 2, "attributes": {"rr_css": "../etc/passwd"}}]) == "rr_css"
    assert unmasked([{"type": 2, "attributes": {"rr_css": "a.css" + "b" * 200}}]) == "rr_css"


def test_changes_to_style_survive_as_rrweb_makes_them() -> None:
    style = {"top": "0px", "left": ["0px", "important"], "right": False}
    assert unmasked([{"data": {"attributes": [{"id": 1, "attributes": {"style": style}}]}}]) is None
    bad = {"content": '"walrus"'}
    changed = {"data": {"attributes": [{"id": 1, "attributes": {"style": bad}}]}}
    assert unmasked([changed]) == "style"
    declaration = {"data": {"source": 13, "set": {"property": "top", "value": "0px"}}}
    assert unmasked([declaration]) is None
    leaked = {"data": {"source": 13, "set": {"property": "top", "value": '"walrus"'}}}
    assert unmasked([leaked]) == "value"
    for bad_change in (["0px"], ["0px", "urgent"], 5):
        odd = {"data": {"attributes": [{"id": 1, "attributes": {"style": {"top": bad_change}}}]}}
        assert unmasked([odd]) == "style", bad_change
    unknown = {"data": {"source": 13, "set": {"property": "content", "value": "none"}}}
    assert unmasked([unknown]) == "property"


def test_a_key_rrwebs_events_do_not_have_is_refused_whatever_it_holds() -> None:
    assert unmasked([{"type": 3, "alice-smith": True}]) == "alice-smith"
    assert unmasked([{"type": 3, "data": {"sparkle": 3}}]) == "sparkle"
    assert unmasked([{"type": 6, "data": {"plugin": "x", "payload": {}}}]) == "plugin"


def test_a_recording_made_in_chromium_passes_and_holds_no_word() -> None:
    # A regression snapshot, not a test that writes it: the events the recorder sent for the page
    # of web/app/src/on-demand/replay-sentinel.test.tsx (a sentence in every attribute), captured
    # once in Chromium by posting them from that test to a local listener. Capture it again when
    # the recorder's output changes shape; it holds the relay's rule to what a browser sent.
    path = Path(__file__).parents[1] / "fixtures" / "replay_chromium.json"
    events = json.loads(path.read_text())
    assert unmasked(events) is None
    assert not re.search(r"walrus|alice|Zq7", json.dumps(events))


class Stack:
    def __init__(self) -> None:
        self.stand = Stand()
        writer = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
        self.replay = InMemoryConsent()
        self.relay = Relay(
            Analytics("http://clickhouse:8123", KEY, writer=writer),
            InMemoryConsent(),
            InMemoryRateLimiter(per_second=1, burst=100),
            umami=umami_of(self.stand),
            replay=self.replay,
        )


@pytest.fixture
def stack() -> Stack:
    return Stack()


@pytest.fixture
async def client(
    grants: Grants, invite: Invite, ui: Path, stack: Stack
) -> AsyncIterator[httpx.AsyncClient]:
    app = app_for(grants, Readers(analytics=stack.relay.analytics), invite, ui, relay=stack.relay)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        yield client


async def replay(client: httpx.AsyncClient, events: list[dict[str, object]]) -> httpx.Response:
    signed = (await client.post("/v1/analytics/session", headers=ALICE)).json()["session"]
    return await client.post(
        "/v1/analytics/replay", json={"session": signed, "events": events}, headers=ALICE
    )


async def test_replay_needs_its_own_yes_after_analytics_and_says_so_in_config(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    assert (await client.get("/config.json")).json()["replay"] is True
    said = await client.put("/v1/analytics/replay/consent", json={"given": True}, headers=ALICE)
    assert said.status_code == 422
    assert said.json()["detail"] == {
        "type": "invalid",
        "message": "replay needs product analytics' yes first",
    }
    await client.put("/v1/analytics/consent", json={"given": True}, headers=ALICE)
    assert (await replay(client, [SNAPSHOT])).json() == {"recorded": 0, "dropped": 1}, (
        "analytics' yes alone"
    )
    said = await client.put("/v1/analytics/replay/consent", json={"given": True}, headers=ALICE)
    assert said.json() == {"given": True, "deleted": None}
    read = await client.get("/v1/analytics/replay/consent", headers=ALICE)
    assert read.json() == {"given": True, "deleting": False}
    assert (await replay(client, [SNAPSHOT, MUTATION, INPUT])).json() == {
        "recorded": 3,
        "dropped": 0,
    }
    await asyncio.gather(*stack.relay.copies)
    assert stack.stand.recorded == [[SNAPSHOT, MUTATION, INPUT]]


async def test_a_batch_with_anything_unmasked_is_dropped_whole_and_said_by_its_key(
    client: httpx.AsyncClient, stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    await stack.relay.consent.give("alice", yes=True)
    await stack.replay.give("alice", yes=True)
    leaked = {"type": 3, "textContent": "Launch on Tuesday"}
    with caplog.at_level(logging.WARNING, logger="portalr.analytics"):
        assert (await replay(client, [SNAPSHOT, leaked])).json() == {"recorded": 0, "dropped": 2}
    await asyncio.gather(*stack.relay.copies)
    assert stack.stand.sent == []
    assert "'textContent' wasn't masked" in caplog.text
    assert "Tuesday" not in caplog.text


async def yes_to_both(stack: Stack) -> None:
    await stack.relay.consent.give("alice", yes=True)
    await stack.replay.give("alice", yes=True)


async def test_a_no_to_replay_deletes_the_persons_sessions_in_umami_and_owes_it_while_down(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    said = await client.put("/v1/analytics/replay/consent", json={"given": False}, headers=ALICE)
    assert said.json() == {"given": False, "deleted": True}
    assert set(stack.stand.sessions) == {"s3"}
    await stack.replay.give("alice", yes=True)
    stack.stand.down = True
    said = await client.put("/v1/analytics/replay/consent", json={"given": False}, headers=ALICE)
    assert said.json() == {"given": False, "deleted": False}
    read = await client.get("/v1/analytics/replay/consent", headers=ALICE)
    assert read.json() == {"given": False, "deleting": True}
    stack.stand.down = False
    assert await stack.relay.settle_owed() == 1
    assert await stack.replay.owes("alice") is None


async def test_a_no_to_analytics_is_a_no_to_replay_too(stack: Stack) -> None:
    await yes_to_both(stack)
    stack.stand.down = True
    await stack.relay.answer("alice", yes=False)
    assert not await stack.replay.given("alice")
    assert await stack.replay.owes("alice") is not None, "owed while Umami is down"


async def test_a_no_to_analytics_deletes_the_replays_at_once_where_umami_can(stack: Stack) -> None:
    await yes_to_both(stack)
    await stack.relay.answer("alice", yes=False)
    assert not await stack.replay.given("alice")
    assert await stack.replay.owes("alice") is None, "not left owed for the menu to say so"


async def test_a_no_while_a_replay_is_sent_deletes_it_from_umami(stack: Stack) -> None:
    await yes_to_both(stack)

    async def says_no() -> None:
        await stack.replay.give("alice", yes=False)
        stack.stand.sessions["s9"] = f"{ACME}:{ME}"

    stack.stand.after_send.append(says_no)
    batch = ReplayBatch(session="s", events=[SNAPSHOT])
    assert (await stack.relay.record_replay("acme", "alice", batch)).recorded == 1
    await asyncio.gather(*stack.relay.copies)
    assert "s9" not in stack.stand.sessions
    assert await stack.replay.owes("alice") is None


async def test_a_replay_is_kept_in_the_session_the_events_are_so_a_deletion_finds_it(
    stack: Stack,
) -> None:
    assert await umami_of(stack.stand).record("acme", ME, [SNAPSHOT])
    visit = next(r for r in stack.stand.sent if r.url.path == "/api/send")
    assert json.loads(visit.content)["payload"]["id"] == f"{ACME}:{ME}"


async def test_a_website_whose_replay_is_off_keeps_none_and_says_so(
    stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    stack.stand.replay_off = True
    assert not await umami_of(stack.stand).record("acme", ME, [SNAPSHOT])
    assert "Umami kept no replay: replay_disabled" in caplog.text


async def test_without_replay_there_are_no_replay_routes_and_config_says_so(
    grants: Grants, invite: Invite, ui: Path
) -> None:
    writer = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    relay = Relay(
        Analytics("http://clickhouse:8123", KEY, writer=writer),
        InMemoryConsent(),
        InMemoryRateLimiter(),
    )
    app = app_for(grants, Readers(analytics=relay.analytics), invite, ui, relay=relay)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        assert (await client.get("/config.json")).json()["replay"] is False
        assert (await client.get("/v1/analytics/replay/consent", headers=ALICE)).status_code == 404
    with pytest.raises(ValueError, match="records no replays"):
        await relay.answer_replay("alice", yes=True)
    assert not await relay.settle_replay("alice", 1)
    assert (
        await relay.record_replay("acme", "alice", ReplayBatch(session="s", events=[SNAPSHOT]))
    ).recorded == 0


async def test_the_replay_routes_refuse_what_the_events_routes_do(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    signed = (await client.post("/v1/analytics/session", headers=ALICE)).json()["session"]
    body = {"session": signed, "events": [SNAPSHOT]}
    no_tenant = await client.post("/v1/analytics/replay", json=body, headers={"x-user": "alice"})
    assert no_tenant.json()["detail"]["type"] == "tenant_required"
    elsewhere = {"x-user": "alice", "x-tenant": "globex"}
    assert (
        await client.post("/v1/analytics/replay", json=body, headers=elsewhere)
    ).status_code == 403
    forged = {"session": "1-0123456789abcdef.forged", "events": [SNAPSHOT]}
    said = await client.post("/v1/analytics/replay", json=forged, headers=ALICE)
    assert (
        said.json()["detail"]["message"] == "the session isn't one portalr signed for this person"
    )


async def test_past_the_most_copies_a_replay_is_dropped(stack: Stack) -> None:
    await yes_to_both(stack)
    held = [asyncio.get_running_loop().create_future() for _ in range(MOST_COPIES)]
    stack.relay.copies.update(held)
    batch = ReplayBatch(session="s", events=[SNAPSHOT])
    assert (await stack.relay.record_replay("acme", "alice", batch)).recorded == 0
    for future in held:
        future.cancel()


class Unreadable(InMemoryConsent):
    """Answers that can't be read again once a replay is sent."""

    reads = 0
    owing_fails = False

    async def given(self, user_id: str) -> bool:
        self.reads += 1
        if self.reads > 1:
            raise RuntimeError(user_id)
        return await super().given(user_id)

    async def owe(self, user_id: str) -> int:
        if self.owing_fails:
            raise RuntimeError(user_id)
        return await super().owe(user_id)


@pytest.mark.parametrize("owing_fails", [False, True])
async def test_a_replays_answer_that_cant_be_read_again_owes_a_deletion_or_says_so(
    owing_fails: bool, caplog: pytest.LogCaptureFixture
) -> None:
    stack = Stack()
    replay = Unreadable()
    replay.owing_fails = owing_fails
    relay = Relay(
        stack.relay.analytics,
        stack.relay.consent,
        InMemoryRateLimiter(),
        umami=umami_of(stack.stand),
        replay=replay,
    )
    await relay.consent.give("alice", yes=True)
    await InMemoryConsent.give(replay, "alice", yes=True)
    assert (
        await relay.record_replay("acme", "alice", ReplayBatch(session="s", events=[SNAPSHOT]))
    ).recorded == 1
    await asyncio.gather(*relay.copies)
    assert "a replay's copy couldn't be checked: RuntimeError" in caplog.text
    if owing_fails:
        assert "a deletion couldn't be owed: RuntimeError" in caplog.text
    else:
        assert await replay.owes("alice") is not None


async def test_a_replay_umami_fails_or_resting_is_none_kept(stack: Stack) -> None:
    stack.stand.down = True
    umami = umami_of(stack.stand)
    assert not await umami.record("acme", ME, [SNAPSHOT])
    stack.stand.down = False
    assert not await umami.record("acme", ME, [SNAPSHOT]), "resting after the failure"


async def test_a_website_whose_replay_is_off_is_not_reported_as_recorded_and_config_says_no(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    stack.stand.replay_off = True
    assert (await client.get("/config.json")).json()["replay"] is False
    assert (await replay(client, [SNAPSHOT])).json() == {"recorded": 0, "dropped": 1}
    await asyncio.gather(*stack.relay.copies)
    assert stack.stand.recorded == [], "nothing is sent to a website that keeps none"


async def test_an_unreachable_umami_means_no_switch_and_none_recorded(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    stack.stand.down = True
    assert (await client.get("/config.json")).json()["replay"] is False
    assert (await replay(client, [SNAPSHOT])).json() == {"recorded": 0, "dropped": 1}


async def test_the_visit_is_sent_once_for_a_persons_batches_and_after_a_no_again(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    for _ in range(3):
        assert (await replay(client, [SNAPSHOT])).json()["recorded"] == 1
        await asyncio.gather(*stack.relay.copies)
    sends = [r for r in stack.stand.sent if r.url.path == "/api/send"]
    assert len(sends) == 1, "one visit for three batches"
    assert len(stack.stand.recorded) == 3
    await client.put("/v1/analytics/replay/consent", json={"given": False}, headers=ALICE)
    await client.put("/v1/analytics/replay/consent", json={"given": True}, headers=ALICE)
    assert (await replay(client, [SNAPSHOT])).json()["recorded"] == 1
    await asyncio.gather(*stack.relay.copies)
    assert len([r for r in stack.stand.sent if r.url.path == "/api/send"]) == 2, (
        "a deleted session's token isn't used again"
    )


async def test_nothing_of_the_person_is_sent_to_umami_but_a_hash_and_portalrs_own_agent(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    headers = {**ALICE, "x-forwarded-for": "203.0.113.9", "user-agent": "Mozilla/5.0 Walrus"}
    signed = (await client.post("/v1/analytics/session", headers=ALICE)).json()["session"]
    await client.post(
        "/v1/analytics/replay", json={"session": signed, "events": [SNAPSHOT]}, headers=headers
    )
    await asyncio.gather(*stack.relay.copies)
    assert stack.stand.sent
    for request in stack.stand.sent:
        assert request.headers["user-agent"] == "portalr-relay"
        assert "x-forwarded-for" not in request.headers
        text = request.content.decode() + str(request.url)
        for word in ("203.0.113.9", "Walrus", "alice", "Mozilla"):
            assert word not in text, word


async def test_a_replay_is_limited_in_bytes_and_in_size_with_texts_of_its_own(
    client: httpx.AsyncClient, stack: Stack
) -> None:
    await yes_to_both(stack)
    signed = (await client.post("/v1/analytics/session", headers=ALICE)).json()["session"]
    big = {"type": 3, "data": {"x": "*" * (MOST_REPLAY_BYTES + 1)}}
    too_large = await client.post(
        "/v1/analytics/replay", json={"session": signed, "events": [big]}, headers=ALICE
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["message"] == f"a batch is {MOST_REPLAY_BYTES} bytes at most"
    chunk = {"type": 3, "data": {"x": "*" * 300_000}}
    statuses = [
        (
            await client.post(
                "/v1/analytics/replay", json={"session": signed, "events": [chunk]}, headers=ALICE
            )
        ).status_code
        for _ in range(6)
    ]
    assert statuses[0] == 202
    assert 429 in statuses, "past a megabyte at once, a person waits"
    responses = openapi_document()["paths"]["/portalr/v1/analytics/replay"]["post"]["responses"]
    assert "512 KiB" in responses["413"]["description"]
    assert "bytes of replay" in responses["429"]["description"]


class NoLandsOnTheSecondRead(InMemoryConsent):
    """Analytics' answers, where a no lands as the second read is made: after a replay's write."""

    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    async def given(self, user_id: str) -> bool:
        self.reads += 1
        if self.reads == 2:
            await self.give(user_id, yes=False)
        return await super().given(user_id)


async def test_an_analytics_no_between_the_check_and_the_write_leaves_no_replay_yes() -> None:
    stand, analytics, replay = Stand(), NoLandsOnTheSecondRead(), InMemoryConsent()
    relay = Relay(
        Analytics("http://clickhouse:8123", KEY),
        analytics,
        InMemoryRateLimiter(),
        umami=umami_of(stand),
        replay=replay,
    )
    await analytics.give("alice", yes=True)
    with pytest.raises(ValueError, match="needs product analytics"):
        await relay.answer_replay("alice", yes=True)
    assert not await replay.given("alice")


async def test_a_replay_is_one_tenants_and_a_removal_deletes_that_tenants_alone(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("portalr.analytics.relay.REMOVAL_GRACE", timedelta(0))
    await yes_to_both(stack)
    batch = ReplayBatch(session="s", events=[SNAPSHOT])
    for tenant in ("acme", "globex"):
        await stack.relay.record_replay(tenant, "alice", batch)
    await asyncio.gather(*stack.relay.copies)
    visits = [
        json.loads(r.content)["payload"]["id"]
        for r in stack.stand.sent
        if r.url.path == "/api/send"
    ]
    assert sorted(visits) == sorted([f"{ACME}:{ME}", f"{GLOBEX}:{ME}"]), "a session for each tenant"
    await stack.relay.removed("globex", "alice")
    assert await stack.relay.settle_owed() == 1
    assert set(stack.stand.sessions) == {"s1", "s3"}, "acme's session stays, globex's is gone"
    stack.stand.sent.clear()
    await stack.relay.record_replay("acme", "alice", batch)
    await asyncio.gather(*stack.relay.copies)
    assert not [r for r in stack.stand.sent if r.url.path == "/api/send"], (
        "acme's visit is still believed"
    )


async def test_a_stylesheet_the_recorder_names_is_given_the_text_of_the_apps_own_file(
    grants: Grants, invite: Invite, ui: Path, stack: Stack
) -> None:
    (ui / "app" / "assets" / "index-ab12.css").write_text(".a{color:red}")
    app = app_for(grants, Readers(analytics=stack.relay.analytics), invite, ui, relay=stack.relay)
    await yes_to_both(stack)
    link = {"type": 2, "attributes": {"rel": "stylesheet", "rr_css": "index-ab12.css"}}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app/portalr"
    ) as client:
        assert (await replay(client, [link])).json() == {"recorded": 1, "dropped": 0}
        await asyncio.gather(*stack.relay.copies)
        forwarded = cast("list[dict[str, Any]]", stack.stand.recorded[-1])
        assert forwarded[0]["attributes"] == {"rel": "stylesheet", "_cssText": ".a{color:red}"}
        unknown = {"type": 2, "attributes": {"rr_css": "nothing-here.css"}}
        assert (await replay(client, [unknown])).json() == {"recorded": 1, "dropped": 0}
        await asyncio.gather(*stack.relay.copies)
        forwarded = cast("list[dict[str, Any]]", stack.stand.recorded[-1])
        assert forwarded[0]["attributes"] == {"_cssText": "x{}"}
        bomb = [{"type": 2, "attributes": {"rr_css": "index-ab12.css"}}] * 9
        assert (await replay(client, bomb)).json() == {"recorded": 0, "dropped": 9}


def test_a_batch_that_names_stylesheets_cannot_grow_past_a_few_files_or_a_megabyte() -> None:
    node = {"type": 2, "attributes": {"rr_css": "a.css"}}
    assert len(json.dumps(node)) < 64, "a name is a few bytes"
    sheets = {"a.css": "x" * 200_000}
    many = [json.loads(json.dumps(node)) for _ in range(MOST_SHEETS + 1)]
    assert expansion(many, sheets) == (MOST_SHEETS + 1, 200_000 * (MOST_SHEETS + 1))
    assert not inlined(many, sheets), "more than a few names"
    assert many[0]["attributes"] == {"rr_css": "a.css"}, "and nothing is put in"
    big = {"a.css": "x" * (MOST_EXPANDED // 2 + 1)}
    two = [json.loads(json.dumps(node)) for _ in range(2)]
    assert not inlined(two, big), "or more than a megabyte of text"
    fits = [json.loads(json.dumps(node)) for _ in range(MOST_SHEETS)]
    assert inlined(fits, {"a.css": "x" * 100_000})


def test_a_key_that_forges_a_log_line_or_floods_it_is_said_short_and_as_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "x\nERROR forged " + "A" * 100_000
    assert unmasked([{"type": 3, key: 1}]) == key
    assert "\n" not in repr(key[:40])
    assert len(repr(key[:40])) < 60


def test_a_style_must_be_ascii_since_a_kelvin_sign_folds_to_a_k() -> None:
    assert _declarations_ok("position: fixed")
    assert not _declarations_ok("position: fixeD".replace("D", "\u212a"))
    assert not _declarations_ok("display: bloc\u212a")


class GivesNoDebt(InMemoryConsent):
    """Replay's answers, where a no finds nothing owed, as when another replica settled it."""

    async def give(self, user_id: str, *, yes: bool) -> int | None:
        await super().give(user_id, yes=yes)
        return None


async def test_a_no_to_analytics_where_replay_owes_nothing_settles_nothing_for_it() -> None:
    stand, replay = Stand(), GivesNoDebt()
    relay = Relay(
        Analytics("http://clickhouse:8123", KEY),
        InMemoryConsent(),
        InMemoryRateLimiter(),
        umami=umami_of(stand),
        replay=replay,
    )
    await relay.consent.give("alice", yes=True)
    await replay.give("alice", yes=True)
    await relay.answer("alice", yes=False)
    assert not await replay.given("alice")
    assert not [r for r in stand.sent if r.method == "DELETE"], "nothing deleted for replay"


async def test_many_asking_whether_umami_keeps_replays_at_once_ask_it_once(stack: Stack) -> None:
    stack.stand.slow = 0.05
    umami = umami_of(stack.stand)
    answers = await asyncio.gather(*(umami.replay_enabled() for _ in range(5)))
    assert answers == [True] * 5
    asked = [r for r in stack.stand.sent if r.method == "GET" and r.url.path.endswith(WEBSITE)]
    assert len(asked) == 1


async def test_the_visits_remembered_are_bounded(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("portalr.readers.umami.MOST_VISITS", 1)
    umami = umami_of(stack.stand)
    assert await umami.record("acme", "one", [SNAPSHOT])
    assert await umami.record("acme", "two", [SNAPSHOT])
    assert len(umami._rest.visits) == 1
