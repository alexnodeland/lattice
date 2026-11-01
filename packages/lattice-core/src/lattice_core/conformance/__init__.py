"""The conformance harness: whether an adapter keeps its port's contract (lattice RFC-0011).

A :class:`Suite` is one port's checks: plain async functions, each given an adapter built fresh
by the adapter's own factory from its configuration, each raising where the adapter breaks the
contract. :func:`run` first checks that the adapter is of the suite's kind and implements the
port's version (:meth:`~lattice_core.adapters.AdapterSpec.supports`), and runs nothing more if
not; then it runs each check, within a time limit, and returns a :class:`Report` of every
result, which never raises for what an adapter does.

The same suite runs under pytest in each adapter's CI, through
:func:`lattice_core.conformance.plugin.conformance_test` (the ``conformance`` extra), and against
a running deployment's adapters, where each check works within an owner of its own that it
removes as it ends, so a store in use is left as it was (lattice ADR-0039). One suite per port:
:data:`lattice_core.conformance.secrets.SECRETS` for :class:`~lattice_core.secrets.Secrets`.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict

from lattice_core.adapters import AdapterKind, AdapterSpec
from lattice_core.capabilities import JsonObject

__all__ = [
    "TIMEOUT",
    "Check",
    "CheckResult",
    "Failed",
    "Report",
    "Suite",
    "expect",
    "refuses",
    "run",
]

TIMEOUT: Final = timedelta(seconds=30)
"""How long one check may take, its adapter's building included, by default."""


class Failed(AssertionError):
    """An adapter broke its port's contract: what a check raises, saying how."""


def expect(condition: bool, message: str) -> None:
    """Raise :class:`Failed` with the message unless the condition holds."""
    if not condition:
        raise Failed(message)


async def refuses(refusal: type[Exception], attempt: Awaitable[object], what: str) -> None:
    """Await an attempt the contract refuses, and raise :class:`Failed` if it isn't refused so.

    Args:
        refusal: The exception the contract says it raises.
        attempt: The call, not yet awaited.
        what: What is attempted, for the message: "a read from another tenant".

    Raises:
        Failed: If it goes ahead, or is refused with another exception.
    """
    try:
        await attempt
    except refusal:
        return
    except Exception as error:
        message = f"{what} raised {type(error).__name__}, not {refusal.__name__}: {error}"
        raise Failed(message) from error
    raise Failed(f"{what} went ahead; it raises {refusal.__name__}")


@dataclass(frozen=True)
class Check[P]:
    """One thing a port's contract says, checked against an adapter built for it alone."""

    name: str
    """What it checks, as a sentence: "a value put is read back within its owner"."""
    run: Callable[[P], Awaitable[None]]
    """The check, given the adapter as the port; it raises where the adapter breaks the
    contract, :class:`Failed` for a broken promise."""


@dataclass(frozen=True)
class Suite[P]:
    """A port's checks, and what an adapter must declare to be checked by them.

    Raises:
        ValueError: If two checks share a name.
    """

    port: str
    """The port's name, as an adapter's ``implements`` names it: ``secrets``."""
    version: str
    """The port's contract version, which an adapter's ``implements`` must cover."""
    kind: AdapterKind
    """The kind of adapter that answers the port."""
    built: Callable[[object], P]
    """The adapter its factory built, as the port; raises :class:`TypeError` if it isn't one."""
    checks: tuple[Check[P], ...]
    """The checks, in the order they run."""

    def __post_init__(self) -> None:
        names = [check.name for check in self.checks]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.port}'s checks are named apart")

    @property
    def implements(self) -> str:
        """The name of the first result, whether the adapter implements the port's version."""
        return f"implements {self.port} {self.version}"


class CheckResult(BaseModel):
    """How an adapter did on one check."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    name: str
    """The check's name."""
    passed: bool
    """Whether the adapter kept the contract."""
    detail: str | None = None
    """How it didn't, where it failed: what was raised, and why."""


class Report(BaseModel):
    """How an adapter did on its port's suite: what ``make validate`` and admin show."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    adapter: str
    """The adapter's name."""
    kind: AdapterKind
    """Its kind."""
    version: str
    """Its version."""
    port: str
    """The port it was checked against."""
    port_version: str
    """The port's contract version."""
    results: tuple[CheckResult, ...]
    """Each result, in order: whether it implements the port's version, then each check run."""

    @property
    def passed(self) -> bool:
        """Whether it passed every check run."""
        return all(result.passed for result in self.results)


def _declared[P](suite: Suite[P], spec: AdapterSpec) -> CheckResult:
    if spec.kind != suite.kind:
        detail = f"{spec.name} is a {spec.kind} adapter, not a {suite.kind} one"
    elif not spec.supports(suite.port, suite.version):
        specifier = spec.implements.get(suite.port, "none of it")
        detail = f"{spec.name} implements {suite.port} {specifier}"
    else:
        return CheckResult(name=suite.implements, passed=True)
    return CheckResult(name=suite.implements, passed=False, detail=detail)


async def _one[P](
    suite: Suite[P], check: Check[P], spec: AdapterSpec, config: JsonObject, limit: timedelta
) -> CheckResult:
    try:
        async with asyncio.timeout(limit.total_seconds()):
            await check.run(suite.built(spec.factory(config)))
    except TimeoutError:
        return CheckResult(name=check.name, passed=False, detail=f"took longer than {limit}")
    except Exception as error:
        detail = f"{type(error).__name__}: {error}"
        return CheckResult(name=check.name, passed=False, detail=detail)
    return CheckResult(name=check.name, passed=True)


async def run[P](
    suite: Suite[P],
    spec: AdapterSpec,
    config: JsonObject | None = None,
    *,
    checks: Iterable[str] | None = None,
    limit: timedelta = TIMEOUT,
) -> Report:
    """Check an adapter against its port's suite, and report how it did.

    Args:
        suite: The port's suite.
        spec: The adapter, as its package declares it.
        config: Its configuration, which its factory builds it from: none if omitted.
        checks: The names of the checks to run; every one if omitted.
        limit: How long each check may take; :data:`TIMEOUT` if omitted.

    Raises:
        ValueError: If ``checks`` names a check the suite doesn't have.
    """
    chosen = suite.checks
    if checks is not None:
        names = set(checks)
        unknown = names - {check.name for check in suite.checks}
        if unknown:
            raise ValueError(f"{suite.port} has no check {', '.join(sorted(unknown))}")
        chosen = tuple(check for check in suite.checks if check.name in names)
    results = [_declared(suite, spec)]
    if results[0].passed:
        results.extend([await _one(suite, check, spec, config or {}, limit) for check in chosen])
    return Report(
        adapter=spec.name,
        kind=spec.kind,
        version=spec.version,
        port=suite.port,
        port_version=suite.version,
        results=tuple(results),
    )
