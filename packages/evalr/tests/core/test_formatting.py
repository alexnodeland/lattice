import re
from typing import Literal

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, Field

from evalr import InputFormatter
from evalr.core import Formatter, estimate_tokens


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Transcript(BaseModel):
    title: str = Field(description="What the thread is about")
    messages: list[Message] = Field(description="Oldest first")
    notes: list[str] = []
    turns: int = 0
    closed: bool | None = None


def transcript(n: int, size: int = 10) -> Transcript:
    return Transcript(
        title="Refund",
        messages=[
            Message(role="user" if i % 2 == 0 else "assistant", content=f"{i}:" + "x" * size)
            for i in range(n)
        ],
        notes=["n1"],
        turns=n,
    )


def words(text: str) -> int:
    return len(text.split())


def test_estimates_are_conservative() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("abcd") == 2
    assert estimate_tokens("日本") == 2


def test_a_small_input_is_rendered_whole() -> None:
    text = InputFormatter()(transcript(2))
    assert text == (
        "## title: What the thread is about\n"
        "Refund\n\n"
        "## messages: Oldest first\n"
        '{"role": "user", "content": "0:xxxxxxxxxx"}\n'
        '{"role": "assistant", "content": "1:xxxxxxxxxx"}\n\n'
        "## notes\n"
        "n1\n\n"
        "## turns\n"
        "2\n\n"
        "## closed\n"
        "null"
    )


def test_fields_are_rendered_separately() -> None:
    fields = InputFormatter().fields(transcript(1))
    assert fields == {
        "title": "Refund",
        "messages": '{"role": "user", "content": "0:xxxxxxxxxx"}',
        "notes": "n1",
        "turns": "1",
        "closed": "null",
    }


def test_long_lists_keep_the_first_and_the_latest_items() -> None:
    formatter = InputFormatter(max_tokens=300)
    fields = formatter.fields(transcript(50))
    lines = fields["messages"].splitlines()
    assert lines[0] == '{"role": "user", "content": "0:xxxxxxxxxx"}'
    assert re.fullmatch(r"\[\.\.\. \d+ earlier items omitted \.\.\.\]", lines[1])
    assert lines[-1] == '{"role": "assistant", "content": "49:xxxxxxxxxx"}'
    assert fields["title"] == "Refund"
    assert sum(map(estimate_tokens, fields.values())) <= 300


def test_long_texts_are_shortened_in_the_middle() -> None:
    class Document(BaseModel):
        body: str

    body = "start " + "middle " * 1000 + "end"
    text = InputFormatter(max_tokens=100)(Document(body=body))
    assert estimate_tokens(text) <= 100
    assert text.startswith("## body\nstart ")
    assert text.endswith("end")
    assert "[... shortened ...]" in text


def test_a_custom_token_counter_sets_the_budget() -> None:
    formatter = InputFormatter(max_tokens=40, count_tokens=words)
    text = formatter(transcript(30))
    assert words(text) <= 40


def test_a_budget_too_small_for_the_headings_gives_what_fits() -> None:
    text = InputFormatter(max_tokens=3)(transcript(5))
    assert estimate_tokens(text) <= 3


def test_a_budget_too_small_for_the_marker_gives_nothing() -> None:
    class Document(BaseModel):
        body: str

    assert InputFormatter(max_tokens=2).fields(Document(body="x" * 100)) == {"body": ""}


def test_an_input_formatter_is_a_formatter() -> None:
    formatter: Formatter[Transcript] = InputFormatter()
    assert formatter(transcript(1)).startswith("## title")


@settings(max_examples=60)
@given(
    st.integers(0, 60),
    st.integers(0, 300),
    st.integers(1, 2_000),
)
def test_the_rendered_text_always_fits_the_budget(n: int, size: int, budget: int) -> None:
    formatter = InputFormatter(max_tokens=budget)
    value = transcript(n, size)
    assert estimate_tokens(formatter(value)) <= budget
    assert sum(map(estimate_tokens, formatter.fields(value).values())) <= budget
