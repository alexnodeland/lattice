"""On PostgreSQL, one person's answer is theirs alone: row-level security, on a real database.

It runs where ``GRANTR_TEST_POSTGRES_URL`` names a PostgreSQL whose user may make roles, as CI's
Check job does; elsewhere it is skipped. It migrates a schema of its own as that user, the
tables' owner, then works as a role that owns nothing, as an application with
``DATABASE_ADMIN_URL`` does.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from portalr.analytics.sql import SqlConsent, SqlReplayConsent, migrate

URL = os.environ.get("GRANTR_TEST_POSTGRES_URL")
ROLE = "portalr_test_application"

pytestmark = pytest.mark.skipif(URL is None, reason="needs GRANTR_TEST_POSTGRES_URL")


@pytest.fixture
async def schema() -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:
    """The owner's engine and the application role's, on a schema made for the test."""
    assert URL is not None
    name = f"portalr_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(URL)
    async with admin.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {name}"))
        exists = await connection.scalar(text(f"SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}'"))
        if not exists:
            await connection.execute(text(f"CREATE ROLE {ROLE} NOLOGIN"))
        await connection.execute(text(f"GRANT USAGE ON SCHEMA {name} TO {ROLE}"))
    owner = create_async_engine(URL, connect_args={"server_settings": {"search_path": name}})
    application = create_async_engine(
        URL, connect_args={"server_settings": {"search_path": name, "role": ROLE}}
    )
    await migrate(owner, application_role=ROLE)
    yield owner, application
    await application.dispose()
    await owner.dispose()
    async with admin.begin() as connection:
        await connection.execute(text(f"DROP SCHEMA {name} CASCADE"))
    await admin.dispose()


async def test_one_person_cant_read_or_write_anothers_answer(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = schema
    consent = SqlConsent(application, owner=owner)
    await consent.give("alice", yes=True)
    assert await consent.given("alice")
    async with application.begin() as connection:
        await connection.execute(text("SELECT set_config('portalr.user_id', 'bob', true)"))
        seen = await connection.scalar(text("SELECT count(*) FROM portalr_analytics_consent"))
        changed = await connection.execute(
            text("UPDATE portalr_analytics_consent SET given = false WHERE user_id = 'alice'")
        )
    assert seen == 0
    assert changed.rowcount == 0
    async with application.begin() as connection:
        with pytest.raises(Exception, match="row-level security"):
            await connection.execute(
                text("INSERT INTO portalr_analytics_consent VALUES ('alice', false, now(), 0, 0)")
            )
    assert await consent.given("alice")


async def test_the_owner_reads_every_deletion_owed(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = schema
    consent = SqlConsent(application, owner=owner)
    owed = []
    for person in ("alice", "bob"):
        await consent.give(person, yes=True)
        debt = await consent.give(person, yes=False)
        assert debt is not None
        owed.append((person, debt))
    assert await consent.owing(100) == owed


OWNERS = {
    "portalr_analytics_removals_owed": "('bob', 'acme', now())",
    "portalr_analytics_audit_cursor": "('acme', 1)",
}
"""The tables the owner alone reads and writes, each with a row to try to insert."""


async def test_what_is_owed_and_read_is_the_owners_alone(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = schema
    consent = SqlConsent(application, owner=owner)
    at = datetime.now(UTC)
    await consent.owe_removal("alice", "acme", at)
    assert await consent.removals_owed(100) == [("alice", "acme", at)]
    await consent.advance_audit("acme", 4)
    assert await consent.audit_cursor("acme") == 4
    for table, row in OWNERS.items():
        for statement in (
            f"SELECT * FROM {table}",
            f"INSERT INTO {table} VALUES {row}",
            f"DELETE FROM {table}",
        ):
            async with application.begin() as connection:
                with pytest.raises(Exception, match="permission denied"):
                    await connection.execute(text(statement))
        async with owner.connect() as connection:
            secured = await connection.scalar(
                text(f"SELECT relrowsecurity FROM pg_class WHERE relname = '{table}'")
            )
            policies = await connection.scalar(
                text(f"SELECT count(*) FROM pg_policies WHERE tablename = '{table}'")
            )
        assert secured, "row-level security, so a grant made by default reads nothing"
        assert policies == 1, (
            "a policy, as stackr's smoke test holds every table of the application's to"
        )
    await consent.removal_settled("alice", "acme", at)
    assert await consent.removals_owed(100) == []


async def test_two_replicas_migrating_at_once_both_succeed(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, _ = schema
    await asyncio.gather(migrate(owner), migrate(owner))


async def test_deletions_owed_at_once_each_take_a_number_of_their_own(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = schema
    consent = SqlConsent(application, owner=owner)
    await consent.give("alice", yes=True)
    numbers = await asyncio.gather(*(consent.owe("alice") for _ in range(20)))
    assert sorted(numbers) == list(range(1, 21))
    assert await consent.owes("alice") == 20


async def test_a_yes_racing_a_deletion_owed_survives_with_the_debt_owed(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = schema
    consent = SqlConsent(application, owner=owner)
    await consent.give("alice", yes=False)
    for _ in range(10):
        _, debt = await asyncio.gather(consent.give("alice", yes=True), consent.owe("alice"))
        given = await consent.given("alice")
        owed = await consent.owes("alice")
        # Whichever ran last, the yes stands and the debt stays owed: a yes never cancels it.
        assert given, "the yes is never lost"
        assert owed == debt
        await consent.give("alice", yes=False)


async def test_replays_answers_are_a_table_of_their_own_and_each_persons_alone(
    schema: tuple[AsyncEngine, AsyncEngine],
) -> None:
    owner, application = schema
    analytics, replay = (
        SqlConsent(application, owner=owner),
        SqlReplayConsent(application, owner=owner),
    )
    await replay.give("alice", yes=True)
    assert await replay.given("alice")
    assert not await analytics.given("alice"), "replay's yes is not analytics'"
    async with application.begin() as connection:
        await connection.execute(text("SELECT set_config('portalr.user_id', 'bob', true)"))
        seen = await connection.scalar(text("SELECT count(*) FROM portalr_replay_consent"))
        changed = await connection.execute(
            text("UPDATE portalr_replay_consent SET given = false WHERE user_id = 'alice'")
        )
    assert seen == 0
    assert changed.rowcount == 0
    async with application.begin() as connection:
        with pytest.raises(Exception, match="row-level security"):
            await connection.execute(
                text("INSERT INTO portalr_replay_consent VALUES ('alice', false, now(), 0, 0)")
            )
    debt = await replay.give("alice", yes=False)
    assert debt is not None
    assert await replay.owing(100) == [("alice", debt)]
    assert await analytics.owing(100) == []
    async with owner.connect() as connection:
        policies = await connection.scalar(
            text("SELECT count(*) FROM pg_policies WHERE tablename = 'portalr_replay_consent'")
        )
    assert policies == 1
