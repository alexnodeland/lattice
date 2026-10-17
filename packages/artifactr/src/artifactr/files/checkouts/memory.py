"""Check-outs in memory, for tests, examples and single-process prototypes."""

from artifactr.files.checkouts.record import Checkout
from artifactr.workspace import Scope


class InMemoryCheckouts:
    """The whole [`Checkouts`][artifactr.files.checkouts.Checkouts] port in memory."""

    def __init__(self) -> None:
        self._checkouts: dict[tuple[Scope, str], Checkout] = {}

    async def save(self, scope: Scope, checkout: Checkout) -> None:
        """Keep a check-out, replacing one with its id."""
        self._checkouts[(scope, checkout.id)] = checkout

    async def get(self, scope: Scope, checkout_id: str) -> Checkout | None:
        """Return a check-out, or None."""
        return self._checkouts.get((scope, checkout_id))
