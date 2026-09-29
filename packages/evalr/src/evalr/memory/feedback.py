"""An in-memory feedback source."""

from collections.abc import AsyncIterator, Iterable

from pydantic import BaseModel

from evalr.core import Example

__all__ = ["InMemoryFeedbackSource"]


class InMemoryFeedbackSource[InputT: BaseModel, VerdictT: BaseModel]:
    """Yields a fixed list of examples, as a library's feedback source would."""

    def __init__(
        self,
        examples: Iterable[Example[InputT, VerdictT]],
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
    ) -> None:
        """Hold the examples to yield.

        Args:
            examples: The feedback, as examples with verdicts.
            input_type: The Pydantic model of the inputs.
            verdict_type: The feedback type.
        """
        self._examples = tuple(examples)
        self._input_type = input_type
        self._verdict_type = verdict_type

    @property
    def input_type(self) -> type[InputT]:
        """The Pydantic model of the inputs."""
        return self._input_type

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The feedback type."""
        return self._verdict_type

    async def examples(self) -> AsyncIterator[Example[InputT, VerdictT]]:
        """Yield the examples, in order."""
        for example in self._examples:
            yield example
