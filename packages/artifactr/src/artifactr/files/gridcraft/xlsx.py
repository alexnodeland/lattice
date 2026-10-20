"""What the adapter reads from a `.xlsx`: its fingerprint, its format, its outline and text.

A `.xlsx` is a zip of XML parts. GridCraft stamps nothing on a save: two saves of the same
workbook are the same bytes, so the fingerprint is the digest of every part.
"""

from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, Field, JsonValue

from artifactr.files.craft import Package
from artifactr.files.manifest import OUTLINE_LIMIT, XLSX

MAIN: Final = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": XLSX,
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml": (
        "application/vnd.ms-excel.sheet.macroEnabled.12"
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template"
    ),
    "application/vnd.ms-excel.template.macroEnabled.main+xml": (
        "application/vnd.ms-excel.template.macroEnabled.12"
    ),
}
"""A spreadsheet package's main part's content type, and the media type of a file it is the
main of."""

XLSX_PACKAGE: Final = Package(".xlsx", main=MAIN)


def media_type(content: bytes) -> str | None:
    """The format a spreadsheet package or an OpenDocument says it is, or None if it says none.

    As [`Package.media_type`][artifactr.files.craft.Package.media_type] reads it.
    """
    return XLSX_PACKAGE.media_type(content)


def fingerprint(content: bytes, *, limit: int) -> str:
    """The digest of a `.xlsx`'s parts, by name.

    As [`Package.fingerprint`][artifactr.files.craft.Package.fingerprint] reads it.
    """
    return XLSX_PACKAGE.fingerprint(content, limit=limit)


class Table(BaseModel):
    """A table of a sheet, as `inspect_workbook` names it."""

    name: str


class Sheet(BaseModel):
    """A sheet of `inspect_workbook`'s summary, as far as the outline reads it."""

    name: str
    used: str | None = Field(default=None, alias="usedRange")
    """The range it uses, such as `A1:D9`; None if it is empty."""
    tables: list[Table] = []


def outline(sheets: Sequence[Sheet]) -> str:
    """Each sheet, with the range it uses, and its tables indented under it."""
    lines: list[str] = []
    for sheet in sheets:
        lines.append(f"{sheet.name} ({sheet.used})" if sheet.used else sheet.name)
        lines += [f"  {table.name}" for table in sheet.tables]
    return "\n".join(lines)[:OUTLINE_LIMIT]


def text(name: str, rows: Sequence[Sequence[JsonValue]]) -> str:
    """A sheet's cells as their app shows them: its name, then a line a row, a tab a cell."""
    return "\n".join(
        [name, *("\t".join("" if cell is None else str(cell) for cell in row) for row in rows)]
    )
