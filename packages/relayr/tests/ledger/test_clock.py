"""Leases expire by the system clock, in UTC, unless a ledger is given another."""

from datetime import UTC, datetime

from relayr.ledger import utc_now


def test_the_default_clock_is_the_systems_in_utc() -> None:
    before = datetime.now(UTC)
    now = utc_now()
    assert now.tzinfo is UTC
    assert before <= now <= datetime.now(UTC)
