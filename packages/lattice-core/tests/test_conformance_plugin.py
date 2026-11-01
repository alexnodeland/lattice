"""The conformance harness under pytest (the ``conformance`` extra): an adapter's own CI collects
a case per check, which fails with what the check found."""

import re
from dataclasses import replace

import pytest
from pydantic import SecretStr

from lattice_core.adapters import AdapterSpec
from lattice_core.conformance.plugin import conformance_test
from lattice_core.conformance.secrets import SECRETS
from lattice_core.secrets import FakeSecrets, Reader, SecretRef

FAKE = AdapterSpec(
    kind="secrets",
    name="fake",
    version="1.0.0",
    implements={"secrets": ">=1,<2"},
    factory=lambda _config: FakeSecrets(),
)

test_the_fake_keeps_the_secrets_contract = conformance_test(SECRETS, FAKE)


class ReadsAnother(FakeSecrets):
    async def read(
        self, ref: SecretRef, /, *, reader: Reader, version: int | None = None
    ) -> SecretStr:
        await super().read(ref, reader=reader, version=version)
        return SecretStr("another")


def test_a_case_per_check_is_collected() -> None:
    [marked] = vars(test_the_fake_keeps_the_secrets_contract)["pytestmark"]
    assert marked.args == ("check", [check.name for check in SECRETS.checks])


def test_a_case_fails_with_what_its_check_found() -> None:
    broken = conformance_test(SECRETS, replace(FAKE, factory=lambda _config: ReadsAnother()))
    name = SECRETS.checks[0].name
    with pytest.raises(
        pytest.fail.Exception, match=re.escape(f"{name}: Failed: read another value")
    ):
        broken(name)


def test_a_case_fails_where_the_adapter_doesnt_implement_the_port() -> None:
    old = conformance_test(SECRETS, replace(FAKE, implements={"secrets": "<1"}))
    with pytest.raises(pytest.fail.Exception, match=r"implements secrets 1\.0\.0: fake implements"):
        old(SECRETS.checks[0].name)
