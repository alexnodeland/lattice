"""portalr's web sources hold no colour literal: a colour is a token, in tokens.css or base.css."""

import re
from pathlib import Path

WEB = Path(__file__).parent.parent / "packages" / "portalr" / "web"

LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\boklch\(|\boklab\(|\blab\(")


def sources() -> list[Path]:
    paths = [
        path
        for package in ("ui", "app", "admin")
        for pattern in ("*.ts", "*.tsx", "*.css")
        for path in (WEB / package / "src").rglob(pattern)
    ]
    return [
        path
        for path in paths
        if ".test." not in path.name
        and "test" not in path.relative_to(WEB).parts
        and path.name not in {"tokens.css", "base.css", "fonts.css", "routeTree.gen.ts"}
    ]


def test_there_are_sources_to_scan() -> None:
    assert len(sources()) > 100


def test_no_source_but_the_tokens_writes_a_colour() -> None:
    found = [
        f"{path.relative_to(WEB)}:{number}: {line.strip()}"
        for path in sources()
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if LITERAL.search(line)
    ]
    assert found == [], "a colour belongs in tokens.css, as a token"


# A Tailwind arbitrary value with a length in px or rem, or a colour mixed in a component: each
# belongs in a token (portalr ADR-0056), so a kit reaches it. tokens.css, base.css and styles.css
# hold them; so far a few measures of layout remain, listed here, which the polish pass moves onto
# tokens, and the editors' and mini apps' frames, whose sizing is left as it is. A new one fails.
ARBITRARY = re.compile(r"[\w:-]*\[[^\]\s\"]*?\d(?:\.\d+)?(?:px|rem)[^\]\s\"]*\]|color-mix\(")
STYLESHEETS = {"tokens.css", "base.css", "styles.css"}
REMAINING = {
    ("app/src/editor-frame.tsx", "h-[min(80dvh,48rem)]"),
    ("app/src/native-inline.tsx", "h-[min(80dvh,48rem)]"),
    ("ui/src/app-shell.tsx", "lg:grid-cols-[15.5rem_minmax(0,1fr)]"),
    ("ui/src/chat.tsx", "max-w-[min(100%,42rem)]"),
    ("ui/src/dashboard-view.tsx", "grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]"),
    ("ui/src/file-preview.tsx", "h-[min(70dvh,32rem)]"),
    ("ui/src/json-view.tsx", "max-h-[32rem]"),
    ("ui/src/line-diff.tsx", "max-h-[32rem]"),
    ("ui/src/log-list.tsx", "lg:grid-cols-[minmax(0,1fr)_22rem]"),
    ("ui/src/log-list.tsx", "max-h-[30rem]"),
    ("ui/src/native-file.tsx", "grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))]"),
    ("ui/src/select-field.tsx", "max-h-[min(18rem,var(--available-height))]"),
    ("ui/src/trace-view.tsx", "lg:grid-cols-[minmax(0,1fr)_22rem]"),
    ("ui/src/trace-view.tsx", "max-h-[28rem]"),
    ("ui/src/trace-view.tsx", "grid-cols-[minmax(0,1fr)_4.5rem]"),
    ("ui/src/trace-view.tsx", "xl:grid-cols-[minmax(11rem,2fr)_minmax(8rem,3fr)_4.5rem]"),
    (
        "ui/src/trace-view.tsx",
        "bg-[repeating-linear-gradient(45deg,var(--fg)_0_3px,var(--surface)_3px_6px)]",
    ),
    ("ui/src/tracker.tsx", "color-mix("),
    ("ui/src/tracker.tsx", "rounded-[1px]"),
}


def test_no_source_but_the_stylesheets_writes_a_length_or_mixes_a_colour() -> None:
    found = {
        (path.relative_to(WEB).as_posix(), literal)
        for path in sources()
        if path.name not in STYLESHEETS
        for literal in ARBITRARY.findall(path.read_text())
    }
    assert found - REMAINING == set(), "a length or a mixed colour belongs in a token"
    assert REMAINING - found == set(), "this one is on a token now: take it off the list"
