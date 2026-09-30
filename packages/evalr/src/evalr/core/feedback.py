"""Datasets from people's feedback, through the ``FeedbackSource`` port."""

from pydantic import BaseModel

from evalr.core.datasets import Dataset
from evalr.core.ports import FeedbackSource

__all__ = ["collect"]


async def collect[InputT: BaseModel, VerdictT: BaseModel](
    name: str, source: FeedbackSource[InputT, VerdictT], *, description: str = ""
) -> Dataset[InputT, VerdictT]:
    """Gather a feedback source's examples into a dataset.

    Args:
        name: The dataset's name.
        source: Where the feedback comes from, such as a library's ``[evals]`` extra.
        description: What the dataset holds.

    Raises:
        DuplicateExample: The source yielded two examples with one id.
    """
    return Dataset(
        name,
        [example async for example in source.examples()],
        input_type=source.input_type,
        verdict_type=source.verdict_type,
        description=description,
    )
