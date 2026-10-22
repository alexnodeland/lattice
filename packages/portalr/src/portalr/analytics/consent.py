"""Whether a person has said yes to product analytics, and whether a deletion of theirs is owed.

A person's answer is no until they say yes. Taking a yes back owes the deletion of their events,
which stays owed, in the same row, until it is done: a deletion ClickHouse couldn't take is
tried again, so a no deletes their events even across an outage (lattice RFC-0008, P5).
"""

from typing import Protocol


class Consent(Protocol):
    """A deployment's people's answers, and the deletions owed them."""

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes; never asked, or no, is ``False``."""
        ...

    async def give(self, user_id: str, *, yes: bool) -> bool:
        """Record the person's answer: whether a deletion of their events is now owed.

        A yes taken back owes one; a no again, or a yes, owes none it didn't already.
        """
        ...

    async def owes(self, user_id: str) -> bool:
        """Whether a deletion of the person's events is owed."""
        ...

    async def settled(self, user_id: str) -> None:
        """Record that the deletion owed the person is done."""
        ...

    async def owing(self) -> list[str]:
        """The people a deletion is owed."""
        ...


class InMemoryConsent:
    """Answers kept in memory, for tests and a prototype; lost when the process stops."""

    def __init__(self) -> None:
        self._answers: dict[str, bool] = {}
        self._owed: set[str] = set()

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes."""
        return self._answers.get(user_id, False)

    async def give(self, user_id: str, *, yes: bool) -> bool:
        """Record the person's answer: whether a deletion is now owed."""
        if not yes and self._answers.get(user_id, False):
            self._owed.add(user_id)
        if yes:
            self._owed.discard(user_id)
        self._answers[user_id] = yes
        return user_id in self._owed

    async def owes(self, user_id: str) -> bool:
        """Whether a deletion of the person's events is owed."""
        return user_id in self._owed

    async def settled(self, user_id: str) -> None:
        """Record that the deletion owed the person is done."""
        self._owed.discard(user_id)

    async def owing(self) -> list[str]:
        """The people a deletion is owed."""
        return sorted(self._owed)
