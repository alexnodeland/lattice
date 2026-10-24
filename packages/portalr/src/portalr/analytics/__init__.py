"""portalr's product analytics, as people's browsers send it (lattice RFC-0008, phase 2).

A browser's events reach ClickHouse only through portalr's relay, ``POST /portalr/v1/events``:
from a signed-in person who has said yes, each named in the registry, its tenant the session's,
its session id one portalr signed for that person, and within a person's pace. Consent is
portalr's own, in the application's database (:mod:`portalr.analytics.sql`), so it is read even
when ClickHouse is down; and withdrawing it deletes the person's events at once.
"""

from portalr.analytics.consent import Consent, InMemoryConsent
from portalr.analytics.limiter import InMemoryRateLimiter, RateLimiter
from portalr.analytics.relay import Relay
from portalr.analytics.stamp import SessionStamp
from portalr.readers.umami import Umami

__all__ = [
    "Consent",
    "InMemoryConsent",
    "InMemoryRateLimiter",
    "RateLimiter",
    "Relay",
    "SessionStamp",
    "Umami",
]
