"""Formatters: the text a judge reads for an input, within a token budget.

Inputs are Pydantic models. A formatter renders one as text for an evaluator, and keeps it within
a budget: a decision model's state is limited (Jev's to 32K tokens), and a language model's
context costs money. Long lists, such as a thread's messages, are windowed first, keeping the
first item and the most recent ones; then the longest text is shortened in the middle.
"""

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, JsonValue

__all__ = ["Formatter", "InputFormatter", "TokenCounter", "estimate_tokens"]

type TokenCounter = Callable[[str], int]
"""Counts the tokens in a text, for a particular model's tokenizer."""


def estimate_tokens(text: str) -> int:
    """Estimate a text's tokens without a tokenizer: one per three bytes of UTF-8, rounded up.

    This overestimates for English prose (about four characters per token) and is close for
    text in scripts that take three bytes a character, so a budget measured with it is rarely
    exceeded. Pass a real tokenizer's counter to a formatter when the limit is exact.
    """
    return math.ceil(len(text.encode()) / 3)


class Formatter[InputT](Protocol):
    """Anything that renders an input as the text a judge reads."""

    def __call__(self, input: InputT, /) -> str:
        """Render the input."""
        ...


_OMITTED = "[... {} earlier items omitted ...]"
_SHORTENED = "[... shortened ...]"


@dataclass(frozen=True, slots=True)
class InputFormatter:
    """Renders any Pydantic model within a token budget.

    Each field is rendered as a section headed by its name and description. Strings are used as
    they are, lists one item to a line, and anything else as JSON. When the whole exceeds the
    budget, the longest list loses its oldest items (after the first, which is usually the
    request), and then the longest remaining text is shortened in the middle, until it fits.

    Attributes:
        max_tokens: The budget for the rendered text.
        count_tokens: How to count tokens; a conservative estimate by default.
    """

    max_tokens: int = 30_000
    count_tokens: TokenCounter = estimate_tokens

    def __call__(self, input: BaseModel, /) -> str:
        """Render the input as one text with a section per field, within the budget."""
        headings = _headings(input)
        overhead = self.count_tokens("\n\n".join(headings.values()))
        fields = self._fit(input, self.max_tokens - overhead)
        text = "\n\n".join(f"{headings[name]}\n{value}" for name, value in fields.items())
        return _shorten(text, self.max_tokens, self.count_tokens)

    def fields(self, input: BaseModel) -> dict[str, str]:
        """Render each field of the input separately, within the budget together.

        Judges that read an input field by field (such as a DSPy signature with one input field
        per field of the model) use this instead of the single text.
        """
        return self._fit(input, self.max_tokens)

    def _fit(self, input: BaseModel, budget: int) -> dict[str, str]:
        items = {name: _items(value) for name, value in input.model_dump(mode="json").items()}
        tokens = {name: [self.count_tokens(i) for i in values] for name, values in items.items()}
        sizes = {name: sum(counts) for name, counts in tokens.items()}
        omitted = dict.fromkeys(items, 0)
        total = sum(sizes.values())
        while total > budget:
            windowable = [name for name, values in items.items() if len(values) > 2]
            if not windowable:
                break
            name = max(windowable, key=sizes.__getitem__)
            del items[name][1]
            removed = tokens[name].pop(1)
            sizes[name] -= removed
            total -= removed
            omitted[name] += 1

        rendered = {name: _join(values, omitted[name]) for name, values in items.items()}
        while (excess := sum(map(self.count_tokens, rendered.values())) - budget) > 0:
            name = max(rendered, key=lambda n: self.count_tokens(rendered[n]))
            size = self.count_tokens(rendered[name])
            if size == 0:
                break
            rendered[name] = _shorten(rendered[name], max(size - excess, 0), self.count_tokens)
        return rendered


def _headings(input: BaseModel) -> dict[str, str]:
    headings: dict[str, str] = {}
    for name, info in type(input).model_fields.items():
        headings[name] = f"## {name}: {info.description}" if info.description else f"## {name}"
    return headings


def _items(value: JsonValue) -> list[str]:
    if isinstance(value, list):
        return [_scalar(v) for v in value]
    return [_scalar(value)]


def _scalar(value: JsonValue) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _join(values: list[str], omitted: int) -> str:
    if omitted:
        values = [values[0], _OMITTED.format(omitted), *values[1:]]
    return "\n".join(values)


def _shorten(text: str, max_tokens: int, count_tokens: TokenCounter) -> str:
    """Cut the middle of a text so that it fits, keeping its start and end."""
    if count_tokens(text) <= max_tokens:
        return text
    if count_tokens(_SHORTENED) > max_tokens:
        return ""
    low, high = 0, len(text)
    while low < high:
        keep = (low + high + 1) // 2
        head, tail = keep - keep // 2, keep // 2
        candidate = f"{text[:head]}{_SHORTENED}{text[len(text) - tail :]}"
        if count_tokens(candidate) <= max_tokens:
            low = keep
        else:
            high = keep - 1
    head, tail = low - low // 2, low // 2
    return f"{text[:head]}{_SHORTENED}{text[len(text) - tail :]}"
