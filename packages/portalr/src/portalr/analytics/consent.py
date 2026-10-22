"""Whether a person has said yes to product analytics: theirs to give and take back, off until."""

from typing import Protocol


class Consent(Protocol):
    """A deployment's people's answers: yes, or anything else, which is no."""

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes; never asked, or no, is ``False``."""
        ...

    async def give(self, user_id: str, *, yes: bool) -> None:
        """Record the person's answer, replacing any before it."""
        ...


class InMemoryConsent:
    """Answers kept in memory, for tests and a prototype; lost when the process stops."""

    def __init__(self) -> None:
        self._answers: dict[str, bool] = {}

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes."""
        return self._answers.get(user_id, False)

    async def give(self, user_id: str, *, yes: bool) -> None:
        """Record the person's answer."""
        self._answers[user_id] = yes
