"""A taint is clean, or tainted with its causes and the hosts it has seen."""

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from lattice_core.taint import Cause, Clean, Taint, Tainted

AT = datetime(2026, 10, 31, 12, tzinfo=UTC)
TAINT: TypeAdapter[Taint] = TypeAdapter(Taint)


def test_a_cause_is_a_capability_or_an_event() -> None:
    assert Cause(capability="web.fetch", at=AT).capability == "web.fetch"
    assert Cause(event="evt_1", at=AT).event == "evt_1"


@pytest.mark.parametrize("given", [{}, {"capability": "web.fetch", "event": "evt_1"}])
def test_a_cause_is_exactly_one_of_them(given: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        Cause.model_validate({**given, "at": AT})


def test_a_taint_is_told_apart_by_its_state() -> None:
    assert TAINT.validate_python({"state": "clean"}) == Clean()
    tainted = TAINT.validate_json(
        '{"state": "tainted", "seen_hosts": ["example.com"],'
        ' "causes": [{"capability": "web.fetch", "at": "2026-10-31T12:00:00Z"}]}'
    )
    assert tainted == Tainted(
        causes=(Cause(capability="web.fetch", at=AT),), seen_hosts=frozenset({"example.com"})
    )


def test_a_tainted_one_has_a_cause() -> None:
    with pytest.raises(ValidationError):
        Tainted(causes=())


def test_the_state_is_required_in_the_schema() -> None:
    assert "state" in Clean.model_json_schema()["required"]
    assert "state" in Tainted.model_json_schema()["required"]
