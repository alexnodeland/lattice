"""Whether a person has said yes to product analytics, and which deletion of theirs is owed.

A person's answer is no until they say yes. Taking a yes back owes the deletion of their events,
which stays owed, in the same row, until it is done: a deletion ClickHouse couldn't take is
tried again, so a no deletes their events even across an outage (lattice RFC-0008, P5).

Each debt is numbered. Settling names the number it started with, and clears the debt only if it
is still that one: a deletion that finishes late never clears a newer debt, owed for events
written after it began.
"""

from typing import Protocol


class Consent(Protocol):
    """A deployment's people's answers, and the deletions owed them, each numbered."""

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes; never asked, or no, is ``False``."""
        ...

    async def give(self, user_id: str, *, yes: bool) -> int | None:
        """Record the person's answer: the deletion now owed them, if any, by its number.

        A yes taken back owes a new one; a no again, or a yes, keeps the one owed, if any: a
        yes never cancels a deletion a no owed.
        """
        ...

    async def owe(self, user_id: str) -> int:
        """Owe the person a new deletion, whatever their answer: its number."""
        ...

    async def owes(self, user_id: str) -> int | None:
        """The deletion owed the person, by its number, if any."""
        ...

    async def settled(self, user_id: str, debt: int) -> None:
        """Record that deletion `debt` is done: cleared only if it is still the one owed."""
        ...

    async def owing(self, most: int) -> list[tuple[str, int]]:
        """At most `most` people a deletion is owed, the longest owed first, with its number."""
        ...


class InMemoryConsent:
    """Answers kept in memory, for tests and a prototype; lost when the process stops."""

    def __init__(self) -> None:
        self._answers: dict[str, bool] = {}
        self._owed: dict[str, int] = {}
        self._last = 0

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes."""
        return self._answers.get(user_id, False)

    async def give(self, user_id: str, *, yes: bool) -> int | None:
        """Record the person's answer: the deletion now owed them, if any."""
        if not yes and self._answers.get(user_id, False):
            await self.owe(user_id)
        self._answers[user_id] = yes
        return self._owed.get(user_id)

    async def owe(self, user_id: str) -> int:
        """Owe the person a new deletion."""
        self._last += 1
        self._owed[user_id] = self._last
        return self._last

    async def owes(self, user_id: str) -> int | None:
        """The deletion owed the person, if any."""
        return self._owed.get(user_id)

    async def settled(self, user_id: str, debt: int) -> None:
        """Clear deletion `debt`, if it is still the one owed."""
        if self._owed.get(user_id) == debt:
            del self._owed[user_id]

    async def owing(self, most: int) -> list[tuple[str, int]]:
        """At most `most` people a deletion is owed, the longest owed first, with its number."""
        return sorted(self._owed.items(), key=lambda owed: owed[1])[:most]
