"""Rejections and identifiers."""

import pickle
from copy import copy as copy_of
from copy import deepcopy

from reflexr.core import (
    DepthExceeded,
    Forbidden,
    InvalidState,
    NotFound,
    Problem,
    Rejection,
    UnsupportedProtocol,
    ValidationFailed,
    firing_id,
    new_event_id,
    new_id,
)


def test_rejections_have_stable_codes_and_payloads() -> None:
    assert Rejection("no").payload() == {"type": "rejected", "message": "no"}
    assert NotFound("run", "fir_1").payload() == {
        "type": "not_found",
        "message": "run fir_1 does not exist",
        "entity": "run",
        "id": "fir_1",
    }
    assert InvalidState("x").code == "invalid_state"
    assert Forbidden("x").code == "forbidden"
    assert UnsupportedProtocol("x").code == "unsupported_protocol"
    assert ValidationFailed("x", [{"loc": ["a"]}]).payload()["errors"] == [{"loc": ["a"]}]
    assert DepthExceeded(9, 8).payload() == {
        "type": "depth_exceeded",
        "message": "the event would be at causation depth 9, beyond the limit of 8",
        "depth": 9,
        "limit": 8,
    }


def test_a_problem_is_its_message_with_the_field_it_names() -> None:
    problem = Problem("timeout is required", "missing", ("timeout",))
    assert problem == "timeout is required"
    assert problem.error() == {"loc": ["timeout"], "msg": "timeout is required", "type": "missing"}
    assert problem.error("rule")["loc"] == ["rule", "timeout"]
    unplaced = Problem("no predicate 'p'", "unknown")
    assert unplaced.error("rule") == {"loc": [], "msg": "no predicate 'p'", "type": "unknown"}
    assert Problem("x", "invalid", ("scope", "fields", 0)).error()["loc"] == ["scope", "fields", 0]


def test_two_problems_with_one_message_are_equal_whatever_else_they_hold() -> None:
    assert Problem("x", "a", ("one",)) == Problem("x", "b", ("two",))


def test_a_problem_survives_copying_and_pickling() -> None:
    problem = Problem("timeout is required", "missing", ("timeout",))
    for copy in (copy_of(problem), deepcopy(problem), pickle.loads(pickle.dumps(problem))):
        assert isinstance(copy, Problem)
        assert (str(copy), copy.type, copy.loc) == ("timeout is required", "missing", ("timeout",))


def test_identifiers() -> None:
    assert new_id("run").startswith("run_")
    assert new_event_id().startswith("evt_")
    assert firing_id("app:r", 0, "[]", 5) == firing_id("app:r", 0, "[]", 5)
    assert firing_id("app:r", 1, "[]", 5) != firing_id("app:r", 0, "[]", 5)
    assert firing_id("app:r", 0, "[]", 5).startswith("fir_")
