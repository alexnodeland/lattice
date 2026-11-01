"""The conformance harness (lattice ADR-0039): the fake secrets store passes the secrets suite,
a store that breaks one rule fails that rule's check, and an adapter that doesn't implement the
port's version is checked no further."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from pydantic import SecretStr

from lattice_core.adapters import AdapterSpec
from lattice_core.capabilities import JsonObject
from lattice_core.conformance import (
    Check,
    CheckResult,
    Failed,
    Report,
    Suite,
    expect,
    refuses,
    run,
)
from lattice_core.conformance.secrets import SECRETS
from lattice_core.secrets import (
    FakeSecrets,
    Owner,
    Reader,
    SecretMetadata,
    SecretRef,
    SecretVersion,
    UnknownSecret,
)

FAKE = AdapterSpec(
    kind="secrets",
    name="fake",
    version="1.0.0",
    implements={"secrets": ">=1,<2"},
    factory=lambda _config: FakeSecrets(),
)
NAMES = [check.name for check in SECRETS.checks]


def _check(start: str) -> str:
    [name] = [name for name in NAMES if name.startswith(start)]
    return name


async def test_the_fake_keeps_the_secrets_contract() -> None:
    report = await run(SECRETS, FAKE)
    assert report.passed, [result for result in report.results if not result.passed]
    assert [result.name for result in report.results] == ["implements secrets 1.0.0", *NAMES]
    assert (report.adapter, report.kind, report.version) == ("fake", "secrets", "1.0.0")
    assert (report.port, report.port_version) == ("secrets", "1.0.0")


async def test_each_check_gets_a_store_of_its_own_and_leaves_nothing_behind() -> None:
    built: list[FakeSecrets] = []

    def factory(config: JsonObject) -> FakeSecrets:
        assert config == {"url": "memory"}
        built.append(FakeSecrets())
        return built[-1]

    report = await run(SECRETS, replace(FAKE, factory=factory), {"url": "memory"})
    assert report.passed
    assert len(built) == len(NAMES)
    assert [store._held for store in built] == [{}] * len(NAMES), "every secret deleted"


# ─── A store that breaks one rule fails its check ──────────────────────────────


class ReadsAnother(FakeSecrets):
    async def read(self, ref: SecretRef, /, *, reader: Reader, version: int | None = None) -> Any:
        await super().read(ref, reader=reader, version=version)
        return SecretStr("another")


class ReadsAnywhere(FakeSecrets):
    async def read(self, ref: SecretRef, /, *, reader: Reader, version: int | None = None) -> Any:
        return await super().read(
            ref,
            reader=reader.model_copy(update={"scope": ref.owner, "purpose": ref.purpose}),
            version=version,
        )


class FindsById(FakeSecrets):
    def _get(self, ref: SecretRef) -> Any:
        if ref.id not in self._held:
            raise UnknownSecret(f"no secret {ref.id}")
        return self._held[ref.id]


class NoGrace(FakeSecrets):
    async def rotate(
        self, ref: SecretRef, value: SecretStr, /, *, grace: timedelta
    ) -> SecretVersion:
        return await super().rotate(ref, value, grace=timedelta(0))


class EndlessGrace(FakeSecrets):
    async def rotate(
        self, ref: SecretRef, value: SecretStr, /, *, grace: timedelta
    ) -> SecretVersion:
        return await super().rotate(ref, value, grace=timedelta(days=365))


class KeepsRevoked(FakeSecrets):
    async def revoke(self, ref: SecretRef, /, *, reason: str) -> None:
        self._get(ref)


class ListsEveryone(FakeSecrets):
    async def list(self, owner: Owner, /) -> list[SecretMetadata]:
        return [held.metadata for held in self._held.values()]


class DeletesEveryone(FakeSecrets):
    async def delete_owned_by(self, owner: Owner, /) -> int:
        count = len(await super().list(owner))
        self._held.clear()
        return count


class RevokesNothing(FakeSecrets):
    async def revoke(self, ref: SecretRef, /, *, reason: str) -> None:
        try:
            await super().revoke(ref, reason=reason)
        except UnknownSecret:
            return


@pytest.mark.parametrize(
    ("store", "breaks"),
    [
        (ReadsAnother, "a value put is read back"),
        (ReadsAnywhere, "a reader outside its owner"),
        (FindsById, "a reference naming another owner"),
        (NoGrace, "a rotation keeps the previous version"),
        (EndlessGrace, "a version past its grace"),
        (KeepsRevoked, "a revocation ends every version"),
        (ListsEveryone, "a listing is every secret"),
        (DeletesEveryone, "deleting what an owner holds"),
        (RevokesNothing, "a reference to no secret"),
    ],
)
async def test_a_store_that_breaks_a_rule_fails_its_check(
    store: type[FakeSecrets], breaks: str
) -> None:
    report = await run(SECRETS, replace(FAKE, factory=lambda _config: store()))
    failed = {result.name: result.detail for result in report.results if not result.passed}
    assert _check(breaks) in failed, f"{store.__name__} passed {breaks!r}"
    assert not report.passed


async def test_what_a_check_found_is_its_detail() -> None:
    spec = replace(FAKE, factory=lambda _config: ReadsAnother())
    report = await run(SECRETS, spec, checks=[_check("a value put is read back")])
    assert report.results[1] == CheckResult(
        name=_check("a value put is read back"), passed=False, detail="Failed: read another value"
    )


async def test_a_factory_that_builds_no_store_fails_every_check() -> None:
    report = await run(SECRETS, replace(FAKE, factory=lambda _config: object()))
    assert {result.detail for result in report.results[1:]} == {
        "TypeError: object isn't a secrets store"
    }


# ─── What an adapter declares ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("changes", "detail"),
    [
        ({"implements": {"secrets": ">=2"}}, "fake implements secrets >=2"),
        ({"implements": {"forge": ">=1"}}, "fake implements secrets none of it"),
        (
            {"kind": "forge", "implements": {"secrets": ">=1"}},
            "fake is a forge adapter, not a secrets one",
        ),
    ],
)
async def test_an_adapter_that_doesnt_implement_the_port_is_checked_no_further(
    changes: dict[str, Any], detail: str
) -> None:
    report = await run(SECRETS, replace(FAKE, **changes))
    assert report.results == (
        CheckResult(name="implements secrets 1.0.0", passed=False, detail=detail),
    )
    assert not report.passed


# ─── The harness ──────────────────────────────────────────────────────────────


async def _waits(_store: object) -> None:
    await asyncio.sleep(1)


async def test_a_check_that_takes_too_long_fails() -> None:
    slow = Suite[object](
        port="secrets",
        version="1.0.0",
        kind="secrets",
        built=lambda b: b,
        checks=(Check("waits", _waits),),
    )
    report = await run(slow, FAKE, limit=timedelta(milliseconds=10))
    assert report.results[1] == CheckResult(
        name="waits", passed=False, detail="took longer than 0:00:00.010000"
    )


async def test_run_runs_the_checks_named() -> None:
    chosen = [_check("a version past its grace"), _check("a value put is read back")]
    report = await run(SECRETS, FAKE, checks=chosen)
    assert [result.name for result in report.results[1:]] == [chosen[1], chosen[0]], "in order"
    with pytest.raises(ValueError, match="secrets has no check nope, nothing"):
        await run(SECRETS, FAKE, checks=["nope", "nothing"])


def test_a_suites_checks_are_named_apart() -> None:
    twice = (Check("waits", _waits), Check("waits", _waits))
    with pytest.raises(ValueError, match="secrets's checks are named apart"):
        Suite[object](
            port="secrets", version="1.0.0", kind="secrets", built=lambda b: b, checks=twice
        )


def test_a_report_passes_when_every_result_does() -> None:
    passed = CheckResult(name="a", passed=True)
    report = Report(
        adapter="fake",
        kind="secrets",
        version="1.0.0",
        port="secrets",
        port_version="1.0.0",
        results=(passed, passed),
    )
    assert report.passed
    assert not report.model_copy(
        update={"results": (passed, CheckResult(name="b", passed=False))}
    ).passed


def test_expect_raises_failed_unless_its_condition_holds() -> None:
    expect(True, "fine")
    with pytest.raises(Failed, match="broken"):
        expect(False, "broken")


async def _raises(error: Exception) -> None:
    raise error


async def _goes_ahead() -> None:
    return None


async def test_refuses_fails_an_attempt_that_goes_ahead_or_is_refused_otherwise() -> None:
    await refuses(UnknownSecret, _raises(UnknownSecret("no secret")), "a read")
    with pytest.raises(Failed, match="a read went ahead; it raises UnknownSecret"):
        await refuses(UnknownSecret, _goes_ahead(), "a read")
    with pytest.raises(Failed, match="a read raised KeyError, not UnknownSecret: 'x'"):
        await refuses(UnknownSecret, _raises(KeyError("x")), "a read")


def test_the_suite_is_the_secrets_contracts() -> None:
    assert (SECRETS.port, SECRETS.kind, SECRETS.implements) == (
        "secrets",
        "secrets",
        "implements secrets 1.0.0",
    )
