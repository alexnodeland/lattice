"""The audit log's types, and the filter a read of it takes."""

from datetime import UTC, datetime
from typing import get_args

from grantr.core import (
    Agent,
    AuditEntry,
    AuditEvent,
    AuditFilter,
    AuditType,
    RulePrincipal,
    ServicePrincipal,
    TenantDeleted,
    User,
)


def test_every_event_type_is_one_a_read_may_keep() -> None:
    events = get_args(get_args(AuditEvent.__value__)[0])
    assert {event.model_fields["type"].default for event in events} == set(
        get_args(AuditType.__value__)
    )


def test_a_filter_keeps_one_subjects_changes_and_tells_a_user_from_a_principal() -> None:
    def by(subject: object) -> AuditEntry:
        at = datetime(2026, 10, 12, tzinfo=UTC)
        return AuditEntry.model_validate(
            {"seq": 1, "at": at, "tenant": "acme", "by": subject, "event": TenantDeleted()}
        )

    alice = AuditFilter(by=User(id="alice"))
    assert alice.keeps(by(User(id="alice")))
    assert not alice.keeps(by(ServicePrincipal(id="alice")))
    assert not alice.keeps(by(None))
    rule = AuditFilter(by=RulePrincipal(workspace="a/b", rule="c"))
    assert not rule.keeps(by(RulePrincipal(workspace="a", rule="b/c")))
    assert AuditFilter(by=Agent()).keeps(by(Agent()))
    assert AuditFilter().keeps(by(None))
    assert not AuditFilter(types=frozenset({"granted"})).keeps(by(None))
