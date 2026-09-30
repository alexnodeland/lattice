"""Minimal type stubs for DSPy's test utilities."""

from typing import Any

from dspy import BaseLM

class DummyLM(BaseLM):
    def __init__(
        self,
        answers: list[dict[str, Any]] | dict[str, dict[str, Any]],
        follow_examples: bool = False,
        reasoning: bool = False,
        adapter: Any = None,
    ) -> None: ...
    def _use_example(self, messages: list[dict[str, Any]]) -> Any: ...
    def _format_answer_fields(self, field_names_and_values: dict[str, Any]) -> Any: ...
