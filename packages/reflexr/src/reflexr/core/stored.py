"""Stored rules: the configuration that allows them, their limits, and how a workspace keeps one.

A stored rule is an ordinary :class:`~reflexr.core.Rule`, installed in one workspace at runtime
rather than registered in code (RFC-0003). What it may do is fixed: the application's
:class:`StoredRules` names the actions and rule namespaces it may use, and constants bound
everything else, the same for every tenant. :func:`check_stored` lists what a rule breaks, so a
draft can be checked before anyone proposes it, and :func:`check_provenance` what a change's
provenance does. A :class:`StoredRule` is one rule as its workspace keeps it: its current version,
whether it is active, and where it came from.
"""

import json
import math
from collections.abc import Mapping, Set
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic_core import to_json, to_jsonable_python

from reflexr.core.conditions import (
    EachPattern,
    Filter,
    PredicateFilter,
    SequencePattern,
    WhereFilter,
    walk,
)
from reflexr.core.errors import InvalidRule, Problem
from reflexr.core.rules import Rule, load_params

MAX_STORED_FIRINGS_PER_HOUR = 60
"""The most firings a stored rule's throttle may allow in an hour."""

MAX_STORED_ATTEMPTS = 5
"""The most attempts a stored rule's retry policy may make of a run."""

MAX_STORED_TIMEOUT = timedelta(minutes=5)
"""The longest timeout a stored rule may give its action."""

MAX_STORED_WINDOW = timedelta(days=1)
"""The longest window a stored rule may use: a pattern's, a dedupe's, or a throttle's period."""

MAX_STORED_DESCRIPTION = 2000
"""The most characters a stored rule's description may have."""

MAX_STORED_BYTES = 16 * 1024
"""The most bytes a stored rule's JSON may have."""

MAX_STORED_PROVENANCE = 4 * 1024
"""The most bytes a change's provenance may have, as JSON."""

MAX_STORED_RULES = 50
"""The most active stored rules a workspace may have."""

_FIXED: dict[str, JsonValue] = {
    "ordering": "none",
    "on_dead_letter": "continue",
    "start": "now",
    "enabled": True,
}
"""The policies every stored rule has: it starts at the head, runs unordered, and never waits
on a dead letter. Archiving is the only way to stop it."""

_HOUR = timedelta(hours=1)


class StoredRule(BaseModel):
    """One stored rule as its workspace keeps it: the current version, and where it came from.

    Storage keeps only the current version, and the log's facts hold the history. Every change
    is a new version, numbered from 1 per workspace and name, and archiving is one too.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: Rule
    """The rule, whose name is the stored rule's."""

    version: int = Field(ge=1)
    """The current version, from 1."""

    status: Literal["active", "archived"] = "active"
    """Whether the rule runs. An archived rule stays stored, so one installed again under its
    name continues its versions."""

    provenance: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    """Where the change came from, as its installer says: opaque JSON that reflexr does not read."""


@dataclass(frozen=True)
class StoredRules:
    """What stored rules may do: the actions they run, and the namespaces they are named in.

    Everything else is fixed by core's limits, the same for every tenant. Who may change them is
    not this configuration's to say: installing, updating, archiving and replaying a rule are
    commands like any other, which ``authorize`` hears with the rule's name.

    Args:
        actions: The only actions stored rules may run, by name, each mapped to the params
            model it declares, or to None if it declares none.
        namespaces: The rule namespaces stored rules may be named in, such as ``{"chat"}``.

    Raises:
        ValueError: If ``namespaces`` includes ``reflexr``, which is reserved.
    """

    actions: Mapping[str, type[BaseModel] | None]
    namespaces: Set[str]

    def __post_init__(self) -> None:
        if "reflexr" in self.namespaces:
            raise ValueError("the reflexr namespace is reserved")


def check_stored(rule: Rule, config: StoredRules) -> list[Problem]:
    """Return every problem with a rule as a stored rule, under ``config`` and core's limits.

    It is pure, beside :meth:`Rule.check`, so a draft can be checked with both before it is
    proposed. The problems follow the rule's fields, each once, and an empty list means the
    rule may be stored.
    """
    namespace = rule.name.partition(":")[0]
    problems: list[Problem] = []
    if namespace not in config.namespaces:
        problems.append(
            Problem(
                f"the namespace {namespace!r} is not one stored rules may use",
                "not_allowed",
                ("name",),
            )
        )
    if len(rule.description) > MAX_STORED_DESCRIPTION:
        problems.append(
            Problem(
                f"description must be at most {MAX_STORED_DESCRIPTION} characters",
                "string_too_long",
                ("description",),
            )
        )
    problems.extend(_condition_problems(rule))
    if rule.scope.fields:
        problems.append(Problem("scope.fields must be empty", "not_allowed", ("scope", "fields")))
    problems.extend(_action_problems(rule, config))
    if rule.retry.max_attempts > MAX_STORED_ATTEMPTS:
        problems.append(
            Problem(
                f"retry.max_attempts must be at most {MAX_STORED_ATTEMPTS}",
                "less_than_equal",
                ("retry", "max_attempts"),
            )
        )
    if rule.timeout is None:
        problems.append(Problem("timeout is required", "missing", ("timeout",)))
    elif rule.timeout > MAX_STORED_TIMEOUT:
        problems.append(
            Problem(
                f"timeout must be at most {to_jsonable_python(MAX_STORED_TIMEOUT)}",
                "less_than_equal",
                ("timeout",),
            )
        )
    held = rule.model_dump(mode="json", include=set(_FIXED))
    problems.extend(
        Problem(f"{name} must be {json.dumps(value)}", "not_allowed", (name,))
        for name, value in _FIXED.items()
        if held[name] != value
    )
    if len(rule.model_dump_json().encode()) > MAX_STORED_BYTES:
        problems.append(
            Problem(f"the rule's JSON must be at most {MAX_STORED_BYTES} bytes", "too_large")
        )
    return list(dict.fromkeys(problems))


def check_provenance(provenance: Mapping[str, JsonValue]) -> list[Problem]:
    """Return the problem with a change's provenance, if its JSON is over core's limit.

    Provenance is opaque to reflexr, so its size is all there is to check. It is measured as a
    rule's JSON is: compact, in UTF-8 bytes.
    """
    if len(to_json(provenance)) > MAX_STORED_PROVENANCE:
        message = f"provenance must be at most {MAX_STORED_PROVENANCE} bytes of JSON"
        return [Problem(message, "too_large")]
    return []


def _condition_problems(rule: Rule) -> list[Problem]:
    """What a stored rule's condition may not have, stage by stage."""
    condition = rule.when
    problems = _filter_problems(condition.filter)
    if condition.dedupe is not None:
        problems.extend(_window_problems(("when", "dedupe", "within"), condition.dedupe.within))
    pattern = condition.pattern
    if isinstance(pattern, SequencePattern):
        for step in pattern.steps:
            problems.extend(_filter_problems(step))
    if not isinstance(pattern, EachPattern):
        problems.extend(_window_problems(("when", "pattern", "within"), pattern.within))
    throttle = condition.throttle
    if throttle is None:
        problems.append(Problem("when.throttle is required", "missing", ("when", "throttle")))
    else:
        problems.extend(_window_problems(("when", "throttle", "per"), throttle.per))
        # at_most firings in any period of per, so that many in each period an hour spans.
        if throttle.at_most * math.ceil(_HOUR / throttle.per) > MAX_STORED_FIRINGS_PER_HOUR:
            limit = MAX_STORED_FIRINGS_PER_HOUR
            problems.append(
                Problem(
                    f"when.throttle must allow at most {limit} firings in any hour",
                    "less_than_equal",
                    ("when", "throttle", "at_most"),
                )
            )
    return problems


def _filter_problems(filter: Filter) -> list[Problem]:
    """The predicates and ``matches`` a filter may not have."""
    filters = list(walk(filter))
    problems = [
        Problem(f"the predicate {f.name!r} is not allowed", "not_allowed")
        for f in filters
        if isinstance(f, PredicateFilter)
    ]
    if any(isinstance(f, WhereFilter) and f.op == "matches" for f in filters):
        problems.append(Problem("the 'matches' operator is not allowed", "not_allowed"))
    return problems


def _window_problems(loc: tuple[str, ...], window: timedelta) -> list[Problem]:
    if window > MAX_STORED_WINDOW:
        message = f"{'.'.join(loc)} must be at most {to_jsonable_python(MAX_STORED_WINDOW)}"
        return [Problem(message, "less_than_equal", loc)]
    return []


def _action_problems(rule: Rule, config: StoredRules) -> list[Problem]:
    """Whether a stored rule's action is allowed, and its params validate as its model."""
    action = rule.then.action
    if action not in config.actions:
        message = f"the action {action!r} is not one stored rules may run"
        return [Problem(message, "not_allowed", ("then", "action"))]
    try:
        load_params(rule, config.actions[action])
    except InvalidRule as invalid:
        return invalid.problems
    return []
