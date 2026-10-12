import pytest

from portalr.tenant import Tenant, allowed


def test_a_tenant_is_made_only_after_a_check() -> None:
    with pytest.raises(TypeError, match="only by allowed"):
        Tenant("acme", allowed=object())


def test_a_tenant_is_its_id() -> None:
    assert allowed("acme") == allowed("acme")
    assert allowed("acme") != allowed("globex")
    assert allowed("acme") != "acme"
    assert len({allowed("acme"), allowed("acme")}) == 1
    assert repr(allowed("acme")) == "Tenant('acme')"


def test_a_tenant_cant_be_changed() -> None:
    tenant = allowed("acme")
    for name in ("_id", "id"):
        with pytest.raises(AttributeError, match="can't be changed"):
            setattr(tenant, name, "globex")
    assert tenant.id == "acme"
