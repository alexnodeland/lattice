"""A person's pace: a bucket of events, refilled with time, per person, in this process."""

from portalr.analytics import InMemoryRateLimiter, RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_burst_is_spent_then_refilled_at_the_rate() -> None:
    clock = Clock()
    limiter: RateLimiter = InMemoryRateLimiter(per_second=2, burst=10, clock=clock)
    assert limiter.spend("alice", 10) is None
    assert limiter.spend("alice", 1) == 0.5
    clock.now = 1.0
    assert limiter.spend("alice", 2) is None
    assert limiter.spend("alice", 1) == 0.5


def test_each_person_has_their_own_bucket() -> None:
    limiter = InMemoryRateLimiter(per_second=1, burst=5, clock=Clock())
    assert limiter.spend("alice", 5) is None
    assert limiter.spend("bob", 5) is None
    assert limiter.spend("alice", 1) == 1.0


def test_it_remembers_so_many_people_forgetting_the_fullest() -> None:
    clock = Clock()
    limiter = InMemoryRateLimiter(per_second=1, burst=5, most_keys=2, clock=clock)
    assert limiter.spend("alice", 5) is None
    assert limiter.spend("bob", 1) is None
    assert limiter.spend("carol", 1) is None
    # bob and carol were fullest; alice, spent, is still held to her empty bucket.
    assert limiter.spend("alice", 1) == 1.0
