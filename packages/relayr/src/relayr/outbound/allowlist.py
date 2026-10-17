"""Allowlists: what each rule may do in artifactr.

artifactr checks a rule's writes to artifacts and proposals against their write policies and
the thread's mode, but not threads, messages or where a rule acts. A rule's allowlist is the
limit on those, so every rule has one: by default, the most restrictive.
"""

import re
from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from reflexr.core import RuleName


class Allowlist(BaseModel):
    """What a rule may do in artifactr.

    The default allows proposals and notices, in the threads of the events that made it fire, and
    nothing more.
    """

    model_config = ConfigDict(frozen=True)

    direct: frozenset[str] = frozenset()
    """The artifact kinds the rule creates and edits directly rather than by proposal.
    artifactr's write policy and the thread's mode still apply."""

    threads: Literal["chain", "any"] = "chain"
    """Where the rule may act: `chain`, the threads of the events that made it fire and those
    it creates, or `any` thread in the workspace."""

    create_threads: bool = False
    """Whether the rule may create threads."""

    turns: bool = False
    """Whether the rule may send messages that start an agent turn, rather than only notices."""


_KEY: Final = re.compile(r"[a-z][a-z0-9_]*:(\*|[a-z0-9][a-z0-9._-]*)")
"""An allowlist's key: a rule's name, as reflexr names rules, or a whole namespace's."""


class Allowlists:
    """Each rule's allowlist, by its name, or by its whole namespace's, as ``"chat:*"``.

    Args:
        allowlists: The allowlists by key. A rule's own name comes first; a rule with neither
            gets the default.

    Raises:
        ValueError: If a key is neither a rule's name nor a whole namespace's, or names
            reflexr's own namespace.
    """

    def __init__(self, allowlists: Mapping[str, Allowlist] | None = None) -> None:
        self._allowlists = dict(allowlists or {})
        for key in self._allowlists:
            if not _KEY.fullmatch(key) or key.startswith("reflexr:"):
                raise ValueError(
                    f"an allowlist's key is a rule's name, as 'chat:deploys', or a whole "
                    f"namespace's, as 'chat:*', and not reflexr's: not {key!r}"
                )

    def of(self, rule: RuleName) -> Allowlist:
        """Return a rule's allowlist: its own, its namespace's, or the default."""
        if rule in self._allowlists:
            return self._allowlists[rule]
        return self._allowlists.get(f"{rule.partition(':')[0]}:*", Allowlist())
