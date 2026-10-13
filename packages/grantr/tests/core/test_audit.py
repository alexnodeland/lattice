"""The audit log's types and actors, as a read of the log names them."""

from typing import get_args

from grantr.core import (
    Agent,
    AuditEvent,
    AuditType,
    RulePrincipal,
    ServicePrincipal,
    User,
    actor_of,
)


def test_every_event_type_is_one_a_read_may_keep() -> None:
    events = get_args(get_args(AuditEvent.__value__)[0])
    assert {event.model_fields["type"].default for event in events} == set(
        get_args(AuditType.__value__)
    )


def test_an_actor_is_named_by_kind_so_a_user_and_a_principal_stay_apart() -> None:
    assert actor_of(User(id="alice")) == "user:alice"
    assert actor_of(ServicePrincipal(id="alice")) == "service_principal:alice"
    assert actor_of(RulePrincipal(workspace="notes", rule="chat:triage")) == (
        "rule:notes/chat:triage"
    )
    assert actor_of(Agent()) == "agent"
    assert actor_of(None) is None
