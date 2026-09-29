"""The ports: what the core needs from the outside, as small protocols.

Adapters implement them in their own packages (ADR-0006): DSPy judges and decision models are
evaluators, Langfuse, Hugging Face and JSON Lines files are dataset stores, and artifactr and
reflexr supply feedback sources. Every port has an in-memory adapter in ``evalr.memory`` and a
contract suite in ``evalr.contracts`` that every adapter passes.

Ports that do I/O are async. Adapters over synchronous SDKs run them in a worker thread.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from evalr.core.datasets import Dataset, Example
from evalr.core.verdicts import Verdict

__all__ = ["DatasetStore", "Evaluator", "FeedbackSource"]


class Evaluator[InputT: BaseModel, VerdictT: BaseModel](Protocol):
    """Judges an input and returns a typed verdict.

    DSPy judges, decision evaluators and function evaluators all implement it, and so can an
    application's own. Evaluators are compared by name and version: a changed evaluator must
    change its version, so that verdicts from before and after never mix.

    An evaluator that declines an input, for another to judge, raises ``HandOff``.
    """

    @property
    def name(self) -> str:
        """The evaluator's name, recorded on every verdict."""
        ...

    @property
    def version(self) -> str:
        """The evaluator's version, recorded on every verdict."""
        ...

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The Pydantic model the evaluator's verdicts are instances of."""
        ...

    async def evaluate(self, input: InputT, /) -> Verdict[VerdictT]:
        """Judge one input."""
        ...


class DatasetStore(Protocol):
    """Saves datasets under their names, and loads them by name and revision.

    Every save makes a revision that can be loaded later, even after further saves, so an
    experiment or a trained judge can name the exact data it used. Saving the same content again
    changes nothing a load can see.
    """

    async def save[InputT: BaseModel, VerdictT: BaseModel](
        self, dataset: Dataset[InputT, VerdictT], /
    ) -> str:
        """Store the dataset under its name, replacing what a load of the name returns.

        Returns:
            The revision just saved, which ``load`` accepts.
        """
        ...

    async def load[InputT: BaseModel, VerdictT: BaseModel](
        self,
        name: str,
        /,
        *,
        input_type: type[InputT],
        verdict_type: type[VerdictT],
        revision: str | None = None,
    ) -> Dataset[InputT, VerdictT]:
        """Load a dataset, validating its examples as the given types.

        Args:
            name: The dataset's name.
            input_type: The Pydantic model of the examples' inputs.
            verdict_type: The Pydantic model of the examples' verdicts.
            revision: A revision ``save`` returned; the latest when ``None``.

        Raises:
            DatasetNotFound: No dataset has the name, or it has no such revision.
            pydantic.ValidationError: The stored examples are not of the given types.
        """
        ...


class FeedbackSource[InputT: BaseModel, VerdictT: BaseModel](Protocol):
    """Yields examples from people's typed feedback.

    The libraries implement it in their ``[evals]`` extras, turning their feedback of one type,
    with the context of its target (a thread, a run), into examples; evalr never imports them.
    Every example has a verdict, its id is stable (derived from the feedback), and iterating
    again yields the same examples.
    """

    @property
    def input_type(self) -> type[InputT]:
        """The Pydantic model of the examples' inputs."""
        ...

    @property
    def verdict_type(self) -> type[VerdictT]:
        """The Pydantic model of the examples' verdicts: the feedback type."""
        ...

    def examples(self) -> AsyncIterator[Example[InputT, VerdictT]]:
        """Yield the examples."""
        ...
