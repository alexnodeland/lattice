"""Results parametrized by their output type can be built through the parametrized alias.

On Python 3.12, a frozen dataclass with slots fails there: typing sets ``__orig_class__`` on the
new instance, and the dataclass's ``__setattr__`` raises ``TypeError`` instead of the
``AttributeError`` typing expects.
"""

from pydantic import BaseModel

from evalr.core import Agreement, ExperimentResult, ItemResult, Measurement


class Answer(BaseModel):
    text: str = ""


def test_results_can_be_built_through_their_parametrized_alias() -> None:
    item = ItemResult[Answer](example_id="e1", output=Answer(text="hi"))
    result = ExperimentResult[Answer](
        name="n", run_name="r", dataset="d", dataset_version="v", items=(item,)
    )
    measurement = Measurement[Answer](
        evaluator="e",
        version="1",
        dataset="d",
        dataset_version="v",
        verdicts={},
        errors={},
        agreement=Agreement(n=0, score=None, fields={}),
        calibration={},
        stats=[],
    )
    assert result.items == (item,)
    assert measurement.verdicts == {}
