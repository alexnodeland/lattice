"""Whether a person has said yes to product analytics, and which deletion of theirs is owed.

A person's answer is no until they say yes. Taking a yes back owes the deletion of their events,
which stays owed, in the same row, until it is done: a deletion ClickHouse couldn't take is
tried again, so a no deletes their events even across an outage (lattice RFC-0008, P5).

Each debt is numbered. Settling names the number it started with, and clears the debt only if it
is still that one: a deletion that finishes late never clears a newer debt, owed for events
written after it began.
"""

from datetime import datetime
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

    async def owe_removal(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        """Owe the deletion of the person's events in the tenant, up to `removed_at`.

        A removal owed already, for a later moment, stays as it is: a deletion owed is never
        owed for less.
        """
        ...

    async def removal_settled(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        """Clear the deletion owed for that removal, only if no later one is owed since."""
        ...

    async def removals_owed(
        self, most: int, *, before: datetime | None = None
    ) -> list[tuple[str, str, datetime]]:
        """At most `most` removals whose deletion is owed, the oldest first, removed `before`."""
        ...

    async def audit_cursor(self, tenant: str) -> int:
        """The `seq` up to which the tenant's audit log has been read for removals; 0 for none."""
        ...

    async def advance_audit(self, tenant: str, seq: int) -> None:
        """Record that the tenant's audit log is read up to `seq`, never back from further."""
        ...


class InMemoryConsent:
    """Answers kept in memory, for tests and a prototype; lost when the process stops."""

    def __init__(self) -> None:
        self._answers: dict[str, bool] = {}
        self._owed: dict[str, int] = {}
        self._last = 0
        self._removals: dict[tuple[str, str], datetime] = {}
        self._audit: dict[str, int] = {}

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

    async def owe_removal(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        """Owe the deletion of the person's events in the tenant, up to `removed_at` or later."""
        key = user_id, tenant
        self._removals[key] = max(removed_at, self._removals.get(key, removed_at))

    async def removal_settled(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        """Clear the deletion owed for that removal, if no later one is owed since."""
        if self._removals.get((user_id, tenant)) == removed_at:
            del self._removals[user_id, tenant]

    async def removals_owed(
        self, most: int, *, before: datetime | None = None
    ) -> list[tuple[str, str, datetime]]:
        """At most `most` removals whose deletion is owed, the oldest first, removed `before`."""
        owed = sorted(
            (item for item in self._removals.items() if before is None or item[1] < before),
            key=lambda removal: (removal[1], removal[0]),
        )
        return [(user_id, tenant, at) for (user_id, tenant), at in owed[:most]]

    async def audit_cursor(self, tenant: str) -> int:
        """The `seq` up to which the tenant's audit log has been read for removals."""
        return self._audit.get(tenant, 0)

    async def advance_audit(self, tenant: str, seq: int) -> None:
        """Record that the tenant's audit log is read up to `seq`, if that is further."""
        self._audit[tenant] = max(seq, self._audit.get(tenant, 0))
