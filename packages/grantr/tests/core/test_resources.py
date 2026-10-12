import pytest
from pydantic import ValidationError

from grantr.core import DEPLOYMENT, TENANT, Resource

WS = Resource(kind="workspace", workspace="w1")
THREAD = Resource(kind="thread", workspace="w1", id="t1")


def test_an_item_is_in_its_workspace_and_its_tenant() -> None:
    assert THREAD.chain() == (THREAD, WS, TENANT)
    assert Resource(kind="rule", workspace="w1", id="ops:page").parent == WS


def test_a_tenant_is_not_in_the_deployment() -> None:
    assert TENANT.chain() == (TENANT,)
    assert DEPLOYMENT.chain() == (DEPLOYMENT,)


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "tenant", "workspace": "w1"},
        {"kind": "deployment", "id": "x"},
        {"kind": "workspace"},
        {"kind": "workspace", "workspace": "w1", "id": "x"},
        {"kind": "artifact", "workspace": "w1"},
        {"kind": "artifact", "id": "a1"},
    ],
)
def test_a_resources_fields_match_its_kind(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="names a workspace if it is in one"):
        Resource.model_validate(fields)
