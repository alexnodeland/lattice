"""Bindings (lattice RFC-0013, ADR-0040): which of a source's events reach which workspace, the
trust a binding lowers them to, and the port three packages read."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from lattice_core.bindings import (
    TRUST_LEVELS,
    Binding,
    Bindings,
    FakeBindings,
    contract_schema,
    lowest,
)

AT = datetime(2026, 11, 1, 6, tzinfo=UTC)


def binding(**changes: Any) -> Binding:
    fields: dict[str, Any] = {
        "id": "bnd_0123456789abcdef",
        "tenant_id": "acme",
        "workspace_id": "api",
        "source": "forge",
        "connection": "inst_1",
        "select": {"repository": "acme/api"},
        "bound_at": AT,
        "by": "user:alice",
    }
    return Binding.model_validate(fields | changes)


def test_a_binding_receives_every_type_and_keeps_its_sources_level_by_default() -> None:
    made = binding()
    assert (made.types, made.trust, made.options) == (None, None, {})
    assert made.level("authenticated") == "authenticated"


def test_a_binding_lowers_its_sources_level_and_never_raises_it() -> None:
    assert binding(trust="untrusted").level("internal") == "untrusted"
    assert binding(trust="internal").level("authenticated") == "authenticated"


def test_the_levels_are_lowest_first() -> None:
    assert TRUST_LEVELS == ("untrusted", "authenticated", "internal")
    assert lowest("internal") == "internal"
    assert lowest("internal", None, "authenticated", "internal") == "authenticated"
    assert lowest("authenticated", "untrusted") == "untrusted"


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"id": "bnd_1"}, "a binding's id is bnd_ and 16 hex digits"),
        ({"source": "Forge"}, "a source's name is lowercase and hyphens"),
        ({"types": frozenset()}, "a binding receives some types"),
        ({"tenant_id": ""}, "at least 1 character"),
        ({"connection": ""}, "at least 1 character"),
        ({"trust": "trusted"}, "'untrusted', 'authenticated' or 'internal'"),
        ({"bound_at": datetime(2026, 11, 1)}, "timezone"),
    ],
)
def test_a_binding_is_refused_unless_well_formed(changes: dict[str, Any], says: str) -> None:
    with pytest.raises(ValidationError, match=says):
        binding(**changes)


async def test_the_fake_answers_by_connection_and_by_workspace_in_the_order_bound() -> None:
    api = binding()
    web = binding(id="bnd_" + "1" * 16, workspace_id="web", select={"repository": "acme/web"})
    other = binding(id="bnd_" + "2" * 16, tenant_id="globex", connection="inst_2")
    tracker = binding(id="bnd_" + "3" * 16, source="tracker", connection="inst_1")
    fake = FakeBindings(api, web, other, tracker)
    assert isinstance(fake, Bindings)
    assert await fake.for_connection("forge", "inst_1") == [api, web]
    assert await fake.for_connection("forge", "inst_2") == [other]
    assert await fake.for_workspace("acme", "api") == [api, tracker]
    assert await fake.for_workspace("globex", "api") == [other]
    assert await fake.for_workspace("acme", "docs") == []
    fake.unbind(api.id)
    assert await fake.for_workspace("acme", "api") == [tracker]
    with pytest.raises(KeyError):
        fake.unbind(api.id)


def test_the_fake_refuses_two_bindings_of_one_id() -> None:
    with pytest.raises(ValueError, match="binding bnd_0123456789abcdef is bound already"):
        FakeBindings(binding(), binding(workspace_id="web"))


def test_the_contracts_schema_is_a_bindings() -> None:
    schema = contract_schema()
    assert schema["title"] == "lattice.bindings 1.0.0"
    assert schema["required"] == [
        "id",
        "tenant_id",
        "workspace_id",
        "source",
        "connection",
        "bound_at",
        "by",
    ]
