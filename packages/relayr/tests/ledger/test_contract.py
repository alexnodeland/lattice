"""The ledger's contract, which every adapter passes: leases, cursors and dead letters."""

from datetime import timedelta

from relayr.ledger import Cause, DeadLetter, Ledger, WorkspaceKey
from tests.clock import FakeClock

PROD = WorkspaceKey("acme", "prod")
STAGING = WorkspaceKey("acme", "staging")
OTHER = WorkspaceKey("globex", "prod")
TTL = timedelta(seconds=30)


def letter(seq: int, error: str = "ValueError: no") -> DeadLetter:
    return DeadLetter(seq=seq, envelope_id=f"evt_{seq}", event_type="app_event", error=error)


async def test_a_workspace_starts_with_nothing(ledger: Ledger) -> None:
    assert await ledger.cursor(PROD) == 0
    assert await ledger.dead_letters(PROD) == []
    assert await ledger.followed() == []


async def test_one_holder_at_a_time_holds_a_lease(ledger: Ledger) -> None:
    assert await ledger.acquire_lease(PROD, "a", TTL)
    assert not await ledger.acquire_lease(PROD, "b", TTL)
    assert await ledger.acquire_lease(PROD, "a", TTL), "its holder renews it"
    assert await ledger.acquire_lease(STAGING, "b", TTL), "each workspace has its own"
    assert await ledger.acquire_lease(OTHER, "b", TTL), "and so does each tenant's"


async def test_a_released_lease_is_free(ledger: Ledger) -> None:
    await ledger.acquire_lease(PROD, "a", TTL)
    await ledger.release_lease(PROD, "b")
    assert not await ledger.acquire_lease(PROD, "b", TTL), "only its holder releases it"
    await ledger.release_lease(PROD, "a")
    assert await ledger.acquire_lease(PROD, "b", TTL)
    await ledger.release_lease(STAGING, "a")  # a workspace the ledger doesn't know


async def test_a_lease_lapses_unless_it_is_renewed(ledger: Ledger, clock: FakeClock) -> None:
    await ledger.acquire_lease(PROD, "a", TTL)
    clock.advance(TTL - timedelta(seconds=1))
    assert not await ledger.acquire_lease(PROD, "b", TTL)
    assert await ledger.acquire_lease(PROD, "a", TTL)
    clock.advance(TTL)
    assert await ledger.acquire_lease(PROD, "b", TTL)
    assert not await ledger.acquire_lease(PROD, "a", TTL)


async def test_a_cursor_only_moves_forward(ledger: Ledger) -> None:
    await ledger.save_cursor(PROD, 5)
    await ledger.save_cursor(PROD, 3)
    assert await ledger.cursor(PROD) == 5
    await ledger.save_cursor(PROD, 8)
    assert await ledger.cursor(PROD) == 8
    assert await ledger.cursor(STAGING) == 0
    assert await ledger.cursor(OTHER) == 0


async def test_a_lease_keeps_the_cursor(ledger: Ledger) -> None:
    await ledger.save_cursor(PROD, 5)
    await ledger.acquire_lease(PROD, "a", TTL)
    await ledger.release_lease(PROD, "a")
    assert await ledger.cursor(PROD) == 5


async def test_followed_workspaces_are_those_with_a_lease_or_a_cursor(ledger: Ledger) -> None:
    await ledger.save_cursor(STAGING, 1)
    await ledger.acquire_lease(OTHER, "a", TTL)
    await ledger.acquire_lease(PROD, "a", TTL)
    await ledger.release_lease(PROD, "a")
    await ledger.dead_letter(WorkspaceKey("acme", "dev"), letter(1))
    assert await ledger.followed() == [PROD, STAGING, OTHER]


async def test_dead_letters_are_kept_once_per_seq_in_order(ledger: Ledger) -> None:
    await ledger.dead_letter(PROD, letter(7))
    await ledger.dead_letter(PROD, letter(2))
    await ledger.dead_letter(PROD, letter(7, "ValueError: again"))
    await ledger.dead_letter(STAGING, letter(1))
    assert await ledger.dead_letters(PROD) == [letter(2), letter(7)]
    assert await ledger.dead_letters(STAGING) == [letter(1)]
    assert await ledger.dead_letters(OTHER) == []


CAUSE = Cause(correlation_id="evt_1", firing_id="fir_1", run_id="fir_1", depth=1)


async def test_a_cause_is_kept_once_per_key(ledger: Ledger) -> None:
    later = CAUSE.model_copy(update={"run_id": "fir_2"})
    await ledger.record_cause(PROD, "message", "7", CAUSE)
    await ledger.record_cause(PROD, "message", "7", later)
    await ledger.record_cause(PROD, "proposal", "7", later)
    assert await ledger.cause(PROD, "message", "7") == CAUSE
    assert await ledger.cause(PROD, "proposal", "7") == later
    assert await ledger.cause(PROD, "turn", "7") is None
    assert await ledger.cause(STAGING, "message", "7") is None
    assert await ledger.followed() == [], "a cause follows no workspace"


async def test_causes_are_forgotten_once_older_than_a_time(
    ledger: Ledger, clock: FakeClock
) -> None:
    await ledger.record_cause(PROD, "message", "old", CAUSE)
    await ledger.record_cause(STAGING, "message", "old", CAUSE)
    clock.advance(timedelta(hours=1))
    await ledger.record_cause(PROD, "message", "new", CAUSE)
    await ledger.forget_causes(PROD, older_than=timedelta(minutes=30))
    assert await ledger.cause(PROD, "message", "old") is None
    assert await ledger.cause(PROD, "message", "new") == CAUSE
    assert await ledger.cause(STAGING, "message", "old") == CAUSE, "only that workspace's"
