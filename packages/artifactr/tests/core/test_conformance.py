"""Runs the language-neutral conformance fixtures in tests/conformance/cases.

Each case gives an actor, the entities that exist, and a command (or a recorded fact), and
expects either an outcome with its events and saved entities, or a rejection. Expected values
are subsets: a case only states the fields it cares about.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter

from artifactr.core import (
    Actor,
    Command,
    CommitResult,
    Fact,
    Proposal,
    Rejection,
    Run,
    State,
    Thread,
    commit,
    load_versioned,
    needs,
    record,
)

CASES = Path(__file__).parent.parent / "conformance" / "cases"


def _cases() -> Iterator[Any]:
    for path in sorted(CASES.glob("*.json")):
        for case in json.loads(path.read_text())["cases"]:
            yield pytest.param(case, id=f"{path.stem}: {case['name']}")


@pytest.mark.parametrize("case", list(_cases()))
def test_conformance(case: dict[str, Any]) -> None:
    actor = TypeAdapter[Actor](Actor).validate_python(case["actor"])
    if "command" in case:
        item: Any = TypeAdapter[Command](Command).validate_python(case["command"])
    else:
        item = TypeAdapter[Fact](Fact).validate_python(case["record"])
    state = _load(item, actor, case.get("given", {}))
    expect = case["expect"]

    def decide() -> CommitResult:
        if "command" in case:
            return commit(item, state, actor=actor)
        return record(item, state, actor=actor)

    if "rejection" in expect:
        with pytest.raises(Rejection) as rejected:
            decide()
        assert_subset(rejected.value.payload(), expect["rejection"])
        return
    result = decide()
    assert_subset(_dump(result.outcome), expect["outcome"])
    if "events" in expect:
        assert_subset([_dump(event) for event in result.events], expect["events"])
    for key in ("artifacts", "revisions", "proposals", "threads", "runs"):
        if key in expect:
            assert_subset([_dump(entity) for entity in getattr(result, key)], expect[key])


def _load(item: Any, actor: Actor, given: dict[str, Any]) -> State:
    """Load what needs() asks for, the way a host would, until nothing more is needed."""
    artifacts = {
        a["id"]: load_versioned(
            id=a["id"],
            kind=a["kind"],
            version=a["version"],
            data=a["data"],
            updated_by=TypeAdapter[Actor](Actor).validate_python(a["updated_by"]),
            archived=a.get("archived", False),
        )
        for a in given.get("artifacts", [])
    }
    proposals = {p["id"]: Proposal.model_validate(p) for p in given.get("proposals", [])}
    threads = {t["id"]: Thread.model_validate(t) for t in given.get("threads", [])}
    runs = {r["id"]: Run.model_validate(r) for r in given.get("runs", [])}
    state = State()
    while missing := needs(item, actor=actor, state=state):
        state = State(
            artifacts={**state.artifacts, **{i: artifacts.get(i) for i in missing.artifacts}},
            proposals={**state.proposals, **{i: proposals.get(i) for i in missing.proposals}},
            threads={**state.threads, **{i: threads.get(i) for i in missing.threads}},
            runs={**state.runs, **{i: runs.get(i) for i in missing.runs}},
        )
    return state


def _dump(value: BaseModel) -> Any:
    return value.model_dump(mode="json")


def assert_subset(actual: Any, expected: Any, path: str = "") -> None:
    """Assert that ``expected`` is contained in ``actual``: dict keys recursively, lists
    element-wise with equal length, and anything else by equality."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected an object, got {actual!r}"
        for key, value in expected.items():
            assert key in actual, f"{path}.{key}: missing in {actual!r}"
            assert_subset(actual[key], value, f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list, got {actual!r}"
        assert len(actual) == len(expected), (
            f"{path}: {len(actual)} items, expected {len(expected)}: {actual!r}"
        )
        for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_subset(a, e, f"{path}[{index}]")
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
