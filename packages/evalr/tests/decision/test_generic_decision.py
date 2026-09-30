"""A decision can be built through its parametrized alias, as results can (Python 3.12)."""

from pydantic import BaseModel

from evalr.decision import Decision


class Answer(BaseModel):
    ok: bool = False


def test_a_decision_can_be_built_through_its_parametrized_alias() -> None:
    decision = Decision[Answer](
        value=Answer(ok=True), confidence={}, probabilities={}, model=None, cost=None
    )
    assert decision.value.ok
