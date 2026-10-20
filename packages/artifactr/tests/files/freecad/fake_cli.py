"""A stand-in for `freecadcmd` running the adapter's script: its steps, as far as the adapter sees.

Its documents are `Document.xml` alone, whose objects are `Object` elements; `box` adds one, and
any other command is refused. Each save writes the time, as FreeCAD's does. A document labelled
`Unsaved` is neither saved nor drawn. Run as `python -I fake_cli.py ... script.py --pass CALL`.
"""

import datetime
import io
import json
import re
import sys
import zipfile
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n"
BLANK = (
    '<Document><Properties><Property name="Label"><String value="document"/></Property>'
    '<Property name="LastModifiedDate"><String value=""/></Property></Properties>'
    "<Objects></Objects></Document>"
)
OBJECT = re.compile(r'<Object type="([^"]+)" name="([^"]+)"')


def main() -> None:
    called = Path(sys.argv[sys.argv.index("--pass") + 1])
    here = called.parent
    call = json.loads(called.read_text())
    source = here / "in" / "document.FCStd"
    document = zipfile.ZipFile(source).read("Document.xml").decode() if source.exists() else BLANK
    if call["label"] is not None:
        document = re.sub(
            r'(name="Label"[^>]*>\s*<String value=")[^"]*',
            rf"\g<1>{call['label']}",
            document,
            count=1,
        )
    result: dict[str, object] = {"version": "1.1.4"}
    try:
        result["result"] = step(here, call, document)
    except ValueError as refused:
        result["refused"] = str(refused)
    (here / "result.json").write_text(json.dumps(result))


def step(here: Path, call: dict, document: str) -> dict:
    unsaved = 'value="Unsaved"' in document
    if call["step"] == "render":
        if not unsaved:
            (here / "out" / "page.png").write_bytes(PNG)
        return {}
    for index, command in enumerate(call.get("commands", [])):
        if command["name"] != "box":
            raise ValueError(f"command {index + 1}: no command {command['name']!r}")
        added = f'<Object type="Part::Box" name="Box{index}"/>'
        document = document.replace("</Objects>", added + "</Objects>")
    if call["step"] == "apply" and not unsaved:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        saved = re.sub(
            r'(name="LastModifiedDate"[^>]*>\s*<String value=")[^"]*',
            rf"\g<1>{now}",
            document,
            count=1,
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(zipfile.ZipInfo("Document.xml"), saved)
        (here / "out" / "document.FCStd").write_bytes(buffer.getvalue())
    objects = [{"name": n, "label": n, "type": t} for t, n in OBJECT.findall(document)]
    return {"objects": objects, "cells": [["Sheet", "A1", "42"]] if objects else []}


main()
