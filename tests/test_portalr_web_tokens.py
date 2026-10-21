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
