"""The `rule` artifact: a reflexr rule drafted in a thread, and the checks a draft must pass."""

from collections.abc import Mapping
from typing import ClassVar

from artifactr import Artifact, WritePolicy
from reflexr import Event, InvalidRule, Rule
from reflexr.core import StoredRules, check_stored


class RuleDraft(Artifact, name="rule"):
    """A reflexr rule, drafted in a thread and reviewed as a proposal before it goes live.

    The type checks the rule's shape alone: artifactr validates an artifact with no access to
    the application's event types or its stored rules' configuration.
    [`check_draft`][relayr.rules.check_draft] checks the rest before the draft is proposed, and
    reflexr checks it all again at install.
    """

    write_policy: ClassVar[WritePolicy] = "propose"

    rule: Rule


def check_draft(
    rule: Rule, *, events: Mapping[str, type[Event]], stored_rules: StoredRules
) -> list[str]:
    """Return every problem with a draft as a stored rule in an application, or none.

    It runs reflexr's two checks of a stored rule: what the rule refers to exists among
    ``events`` and the actions ``stored_rules`` allows, and the rule keeps within reflexr's
    limits on stored rules.

    Args:
        rule: The draft.
        events: The event types the application's reflexr workspaces accept, by name.
        stored_rules: The application's configuration of stored rules.
    """
    problems: list[str] = []
    try:
        rule.check(events=events, actions=stored_rules.actions)
    except InvalidRule as invalid:
        problems.extend(invalid.problems)
    return [*problems, *check_stored(rule, stored_rules)]
