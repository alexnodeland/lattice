"""The first filter on an app's HTML: what it would load from outside, each place named."""

import pytest

from artifactr.ui._html import loaded, refused

PNG = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.parametrize(
    "html",
    [
        '<!doctype html><button disabled onclick="go()">Roll</button><script>go()</script>',
        f'<img src="{PNG}" srcset="{PNG} 1x, {PNG} 2x"><a href="#top">Up</a>',
        f'<img srcset="{PNG} 1x,{PNG} 2x, " alt="">',
        "<style>body { background: url(data:image/png;base64,AA//) }</style>",
        "<a href='javascript:void(0)' style=\"background: url('#grain')\">Go</a>",
        '<a href="mailto:ops@example.com">Mail</a> <a href="tel:+441234">Ring</a>',
        '<link rel="icon" href="about:blank"><img src="" alt="">',
        "<p>See https://example.com, in words only.</p>",
        "<script>const site = 'https://example.com'; import('./local.js')</script>",
        '<script type="importmap">{"imports": {"dice": "data:text/javascript,export{}"}}</script>',
        '<script type="importmap">not a map</script>',
        '<script type="importmap">{"imports": {}, "count": 1}</script>',
        '<iframe srcdoc="<b>Hi</b>"></iframe>',
    ],
)
def test_html_that_holds_what_it_needs_loads_nothing(html: str) -> None:
    assert loaded(html) == []
    assert refused(html) is None


@pytest.mark.parametrize(
    ("html", "named"),
    [
        ('<script src="https://cdn.example/x.js"></script>', "<script src>: https://cdn"),
        ('<link rel="stylesheet" href="//fonts.example/css">', "<link href>: //fonts"),
        ('<img src="cat.png">', "<img src>: cat.png"),
        (f'<img srcset="{PNG} 1x, https://e.example/2.png 2x">', "<img srcset>: https://e"),
        ('<img srcset="data:a 1x,https://e.example/2.png 2x">', "<img srcset>: https://e"),
        ('<img srcset="https://e.example/a.png, data:b">', "<img srcset>: https://e"),
        ('<a href="/" ping="https://e.example/p">x</a>', "<a href>: /; <a ping>: https://e"),
        ('<form action="https://e.example/f"></form>', "<form action>: https://e"),
        ("<div style=\"background:url( 'https://e.example/b' )\">", "<div style>: https://e"),
        ("<style>@import 'https://e.example/s.css';</style>", "<style>: https://e"),
        ('<style>p { background: image-set("x.png" 1x) }</style>', "<style>: x.png"),
        ("<style>p { background: image-set('data:a' 1x, 'b.png' 2x) }</style>", "<style>: b.png"),
        ('<meta http-equiv="Refresh" content="0;url=https://e">', "<meta http-equiv>: a refresh"),
        ('<object data="https://e.example/o"></object>', "<object data>: https://e"),
        ('<base href="https://e.example/">', "<base href>: https://e"),
        (
            '<script type="module">import * as THREE from "https://unpkg.com/three";</script>',
            "<script> import: https://unpkg.com/three",
        ),
        ("<script>await import('//esm.example/x')</script>", "<script> import: //esm"),
        (
            '<script type="importmap">{"scopes": {"/": {"x": "https://esm.example/x"}}}</script>',
            "<script type=importmap>: https://esm",
        ),
        ("<iframe srcdoc=\"<img src='https://e.example/i'>\"></iframe>", "<iframe srcdoc>: <img"),
    ],
)
def test_html_that_loads_from_outside_is_refused_with_what_it_loads(html: str, named: str) -> None:
    why = refused(html)
    assert why is not None
    assert "can load nothing" in why
    assert named in why
