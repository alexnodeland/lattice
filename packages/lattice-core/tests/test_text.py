"""holds_nul: a NUL character anywhere in the text a value holds."""

import pytest
from pydantic import BaseModel

from lattice_core.text import holds_nul

NUL = "a\x00b"


class Note(BaseModel):
    title: str
    tags: list[str] = []


@pytest.mark.parametrize(
    "values",
    [
        (NUL,),
        ("fine", NUL),
        (Note(title=NUL),),
        (Note(title="fine", tags=["x", NUL]),),
        ({"key": NUL},),
        ({NUL: "value"},),
        ([["deep", [NUL]]],),
        ({("a", NUL)},),
    ],
)
def test_a_nul_anywhere_is_found(values: tuple[object, ...]) -> None:
    assert holds_nul(*values)


@pytest.mark.parametrize(
    "values",
    [(), ("fine",), (Note(title="fine", tags=["x"]),), ({"key": ["v"]},), (b"a\x00b",), (1, None)],
)
def test_text_without_a_nul_and_bytes_pass(values: tuple[object, ...]) -> None:
    assert not holds_nul(*values)


def test_deep_data_cannot_exhaust_recursion() -> None:
    nested: list[object] = ["fine"]
    for _ in range(10_000):
        nested = [nested]
    assert not holds_nul(nested)
