"""Allowlists: what each rule may do in artifactr.

artifactr checks a rule's writes to artifacts and proposals against their write policies and
the thread's mode, but not threads, messages or where a rule acts. A rule's allowlist is the
limit on those, so every rule has one: by default, the most restrictive.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


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
