"""GridCraft's corpus: one generated `.xlsx` per feature, beside this, each holding that feature.

Every file is written by hand, part by part, from the SpreadsheetML schema's smallest valid
shapes, with a fixed time on every zip entry, so the same code makes the same bytes. A test
fails if the committed files drift from what this makes;
`python -m tests.files.corpus.gridcraft.make`, from `packages/artifactr`, writes them again.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from tests.files.corpus.package import RELS, XML, relationships, types, zipped

HERE: Final = Path(__file__).parent

S: Final = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAIN: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml"

STYLES: Final = (
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00 &quot;EUR&quot;"/></numFmts>'
    '<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font>'
    '<font><i/><sz val="11"/><color rgb="FFFF0000"/><name val="Calibri"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/></patternFill></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
    '</cellXfs><dxfs count="1"><dxf><font><b/></font></dxf></dxfs>'
)
"""The styles every file shares: by index, plain, euros, a percentage, a date, bold, and red
italics on yellow; and bold, for a conditional format."""


@dataclass(frozen=True)
class Sheet:
    """A sheet: its cells, by reference, and what its XML holds around and after them."""

    name: str
    cells: Mapping[str, str | float | bool] = field(default_factory=dict[str, str | float | bool])
    """Each cell's value: text, a number, a boolean, or a formula, `=` first."""

    styled: Mapping[str, int] = field(default_factory=dict[str, int])
    """Each cell's style, by its index in `STYLES`' cell formats."""

    head: str = ""
    """What comes before its data: its views and its columns."""

    tail: str = ""
    """What comes after its data: merges, validations, links and the parts it names."""

    rows: Mapping[int, float] = field(default_factory=dict[int, float])
    """Each row's height, where it has one."""

    parts: Mapping[str, tuple[str, str, str]] = field(
        default_factory=dict[str, tuple[str, str, str]]
    )
    """The parts it names, `{id: (type, target, content)}`, beside its own in `xl/`."""

    links: Mapping[str, str] = field(default_factory=dict[str, str])
    """Its external links, `{id: url}`."""

    state: str = ""


def column(ref: str) -> str:
    return ref.rstrip("0123456789")


def row(ref: str) -> int:
    return int(ref[len(column(ref)) :])


def cell(ref: str, value: str | float | bool, style: int, strings: list[str]) -> str:
    """A cell's XML: its text among the shared strings, its number, its boolean, or its formula."""
    s = f' s="{style}"' if style else ""
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, float | int):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    if value.startswith("="):
        return f'<c r="{ref}"{s}><f>{value[1:]}</f></c>'
    if value not in strings:
        strings.append(value)
    return f'<c r="{ref}"{s} t="s"><v>{strings.index(value)}</v></c>'


def worksheet(sheet: Sheet, strings: list[str]) -> str:
    rows: dict[int, list[str]] = {}
    for ref, value in sheet.cells.items():
        rows.setdefault(row(ref), []).append(cell(ref, value, sheet.styled.get(ref, 0), strings))
    for number in sheet.rows:
        rows.setdefault(number, [])
    data = "".join(
        f'<row r="{number}"'
        + (f' ht="{sheet.rows[number]}" customHeight="1"' if number in sheet.rows else "")
        + f">{''.join(rows[number])}</row>"
        for number in sorted(rows)
    )
    return (
        f'{XML}<worksheet xmlns="{S}" xmlns:r="{R}">{sheet.head}'
        f"<sheetData>{data}</sheetData>{sheet.tail}</worksheet>"
    )


def workbook(*sheets: Sheet, names: str = "") -> bytes:
    """A `.xlsx` of the sheets, in order, and the workbook's defined names."""
    strings: list[str] = []
    files: dict[str, str] = {}
    overrides = {"xl/workbook.xml": f"{MAIN}.sheet.main+xml", "xl/styles.xml": f"{MAIN}.styles+xml"}
    targets = {"rId1": ("styles", "styles.xml")}
    listed: list[str] = []
    for number, sheet in enumerate(sheets, 1):
        target = f"worksheets/sheet{number}.xml"
        files[f"xl/{target}"] = worksheet(sheet, strings)
        overrides[f"xl/{target}"] = f"{MAIN}.worksheet+xml"
        targets[f"rId{number + 2}"] = ("worksheet", target)
        state = f' state="{sheet.state}"' if sheet.state else ""
        listed.append(
            f'<sheet name="{sheet.name}" sheetId="{number}"{state} r:id="rId{number + 2}"/>'
        )
        own: dict[str, tuple[str, str]] = {}
        for rid, (kind, part, content) in sheet.parts.items():
            own[rid] = (kind, f"../{part}")
            files[f"xl/{part}"] = content
            overrides[f"xl/{part}"] = f"{MAIN}.{kind}+xml"
        if own or sheet.links:
            links = {rid: ("hyperlink", url) for rid, url in sheet.links.items()}
            files[f"xl/worksheets/_rels/sheet{number}.xml.rels"] = relationships(own, links)
    if strings:
        targets["rId2"] = ("sharedStrings", "sharedStrings.xml")
        overrides["xl/sharedStrings.xml"] = f"{MAIN}.sharedStrings+xml"
        files["xl/sharedStrings.xml"] = (
            f'{XML}<sst xmlns="{S}" count="{len(strings)}" uniqueCount="{len(strings)}">'
            + "".join(f"<si><t>{s}</t></si>" for s in strings)
            + "</sst>"
        )
    return zipped(
        {
            "[Content_Types].xml": types({"rels": RELS, "xml": "application/xml"}, overrides),
            "_rels/.rels": relationships({"rId1": ("officeDocument", "xl/workbook.xml")}),
            "xl/workbook.xml": (
                f'{XML}<workbook xmlns="{S}" xmlns:r="{R}"><sheets>{"".join(listed)}</sheets>'
                f"{names}</workbook>"
            ),
            "xl/_rels/workbook.xml.rels": relationships(targets),
            "xl/styles.xml": f'{XML}<styleSheet xmlns="{S}">{STYLES}</styleSheet>',
            **files,
        }
    )


def values() -> bytes:
    cells = {"A1": "Item", "B1": "Fee", "C1": "Paid", "A2": "Setup", "B2": 100.0, "C2": True}
    return workbook(Sheet("Fees", cells | {"A3": "Support", "B3": 20.5, "C3": False}))


def formulas() -> bytes:
    cells = {
        "A1": 100.0,
        "A2": 20.0,
        "A3": "=SUM(A1:A2)",
        "B1": "=A1*2",
        "B2": '=IF(A2>10,"high","low")',
    }
    return workbook(Sheet("Sums", cells))


def number_formats() -> bytes:
    cells = {"A1": 1234.5, "A2": 0.25, "A3": 46000.0}
    return workbook(Sheet("Formats", cells, styled={"A1": 1, "A2": 2, "A3": 3}))


def fonts_and_fills() -> bytes:
    cells = {"A1": "Bold", "A2": "Red on yellow", "A3": "Plain"}
    return workbook(Sheet("Styled", cells, styled={"A1": 4, "A2": 5}))


def sheets() -> bytes:
    return workbook(
        Sheet("First", {"A1": "One"}),
        Sheet("Second", {"A1": "Two"}),
        Sheet("Hidden", {"A1": "Three"}, state="hidden"),
    )


def merges() -> bytes:
    cells = {"A1": "Merged across", "A3": "Merged down"}
    tail = '<mergeCells count="2"><mergeCell ref="A1:C1"/><mergeCell ref="A3:A5"/></mergeCells>'
    return workbook(Sheet("Merged", cells, tail=tail))


def sizes() -> bytes:
    head = (
        '<cols><col min="1" max="1" width="30" customWidth="1"/>'
        '<col min="3" max="4" width="5" customWidth="1"/></cols>'
    )
    return workbook(Sheet("Sized", {"A1": "Wide", "C2": "Narrow"}, head=head, rows={2: 40.0}))


def freeze_panes() -> bytes:
    head = (
        '<sheetViews><sheetView workbookViewId="0"><pane xSplit="1" ySplit="1" '
        'topLeftCell="B2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
    )
    return workbook(Sheet("Frozen", {"A1": "Corner", "B1": "Header", "A2": "Label"}, head=head))


def defined_names() -> bytes:
    names = (
        '<definedNames><definedName name="Rate">Rates!$B$1</definedName>'
        '<definedName name="Table">Rates!$A$1:$B$2</definedName></definedNames>'
    )
    return workbook(
        Sheet("Rates", {"A1": "Rate", "B1": 0.2, "A2": "Base", "B2": 50.0}), names=names
    )


def comments() -> bytes:
    notes = (
        f'{XML}<comments xmlns="{S}"><authors><author>Ada</author></authors><commentList>'
        '<comment ref="B2" authorId="0"><text><r><t>Check this fee.</t></r></text></comment>'
        "</commentList></comments>"
    )
    sheet = Sheet(
        "Noted",
        {"A2": "Setup", "B2": 100.0},
        parts={"rId1": ("comments", "comments1.xml", notes)},
    )
    return workbook(sheet)


def data_validation() -> bytes:
    tail = (
        '<dataValidations count="2"><dataValidation type="list" allowBlank="1" sqref="A2:A9">'
        '<formula1>"Yes,No"</formula1></dataValidation><dataValidation type="whole" '
        'operator="between" sqref="B2:B9"><formula1>1</formula1><formula2>10</formula2>'
        "</dataValidation></dataValidations>"
    )
    return workbook(Sheet("Checked", {"A1": "Answer", "B1": "Score"}, tail=tail))


def conditional_formatting() -> bytes:
    tail = (
        '<conditionalFormatting sqref="A1:A5"><cfRule type="cellIs" dxfId="0" priority="1" '
        'operator="greaterThan"><formula>10</formula></cfRule></conditionalFormatting>'
    )
    cells = {f"A{n}": float(n * 4) for n in range(1, 6)}
    return workbook(Sheet("Highlighted", cells, tail=tail))


def tables() -> bytes:
    table = (
        f'{XML}<table xmlns="{S}" id="1" name="Fees" displayName="Fees" ref="A1:B3">'
        '<autoFilter ref="A1:B3"/><tableColumns count="2"><tableColumn id="1" name="Item"/>'
        '<tableColumn id="2" name="Fee"/></tableColumns><tableStyleInfo name="TableStyleMedium2" '
        'showRowStripes="1"/></table>'
    )
    cells = {"A1": "Item", "B1": "Fee", "A2": "Setup", "B2": 100.0, "A3": "Support", "B3": 20.0}
    sheet = Sheet(
        "Tabled",
        cells,
        tail='<tableParts count="1"><tablePart r:id="rId1"/></tableParts>',
        parts={"rId1": ("table", "tables/table1.xml", table)},
    )
    return workbook(sheet)


def hyperlinks() -> bytes:
    tail = (
        '<hyperlinks><hyperlink ref="A1" r:id="rId9"/>'
        '<hyperlink ref="A2" location="Linked!B5"/></hyperlinks>'
    )
    sheet = Sheet(
        "Linked",
        {"A1": "The site", "A2": "Further down"},
        tail=tail,
        links={"rId9": "https://example.com/"},
    )
    return workbook(sheet)


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "values": values,
    "formulas": formulas,
    "number_formats": number_formats,
    "fonts_and_fills": fonts_and_fills,
    "sheets": sheets,
    "merges": merges,
    "sizes": sizes,
    "freeze_panes": freeze_panes,
    "defined_names": defined_names,
    "comments": comments,
    "data_validation": data_validation,
    "conditional_formatting": conditional_formatting,
    "tables": tables,
    "hyperlinks": hyperlinks,
}
"""Each feature RFC-0003's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.xlsx").write_bytes(make())


if __name__ == "__main__":
    main()
