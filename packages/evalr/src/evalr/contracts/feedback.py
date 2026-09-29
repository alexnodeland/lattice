"""The ``FeedbackSource`` contract."""

from pydantic import BaseModel

from evalr.contracts.support import require
from evalr.core import Example, FeedbackSource, verdict_fields

__all__ = ["check_feedback_source"]


async def check_feedback_source[InputT: BaseModel, VerdictT: BaseModel](
    source: FeedbackSource[InputT, VerdictT],
) -> None:
    """Check that a feedback source yields well-formed, stable examples with verdicts.

    Raises:
        ContractViolation: The source behaves differently from the ``FeedbackSource`` contract.
        UnsupportedField: The source's verdict type cannot be judged.
    """
    verdict_fields(source.verdict_type)
    first = [example async for example in source.examples()]
    ids = [example.id for example in first]
    require(len(set(ids)) == len(ids), "example ids must be unique")
    for example in first:
        _require_well_formed(source, example)
    again = {example.id: example async for example in source.examples()}
    require(
        again == {example.id: example for example in first},
        "iterating again must yield the same examples",
    )


def _require_well_formed[InputT: BaseModel, VerdictT: BaseModel](
    source: FeedbackSource[InputT, VerdictT], example: Example[InputT, VerdictT]
) -> None:
    require(
        isinstance(example.input, source.input_type),
        f"{example.id}: the input must be a {source.input_type.__name__}",
    )
    require(
        isinstance(example.verdict, source.verdict_type),
        f"{example.id}: the verdict must be a {source.verdict_type.__name__}",
    )
