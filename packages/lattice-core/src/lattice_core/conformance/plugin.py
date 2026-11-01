"""The conformance harness under pytest, for an adapter's own CI: the ``conformance`` extra.

An adapter's test module assigns :func:`conformance_test`'s test to a name pytest collects, and
each of the suite's checks is a case of its own, failing with what the check found::

    from lattice_core.conformance.plugin import conformance_test
    from lattice_core.conformance.secrets import SECRETS

    test_vault_keeps_the_secrets_contract = conformance_test(SECRETS, VAULT, {"url": URL})

Each case runs its check in an event loop of its own, so it needs no async plugin.
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta

import pytest

from lattice_core.adapters import AdapterSpec
from lattice_core.capabilities import JsonObject
from lattice_core.conformance import TIMEOUT, Suite, run

__all__ = ["conformance_test"]


def conformance_test[P](
    suite: Suite[P],
    spec: AdapterSpec,
    config: JsonObject | None = None,
    *,
    limit: timedelta = TIMEOUT,
) -> Callable[[str], None]:
    """Return a test of the adapter against the suite, with a case for each check.

    Each case fails if the adapter doesn't implement the port's version, or breaks the check.

    Args:
        suite: The port's suite.
        spec: The adapter.
        config: Its configuration, which its factory builds it from.
        limit: How long each check may take; :data:`~lattice_core.conformance.TIMEOUT` if
            omitted.
    """

    @pytest.mark.parametrize("check", [check.name for check in suite.checks])
    def test(check: str) -> None:
        report = asyncio.run(run(suite, spec, config, checks=[check], limit=limit))
        failed = [
            f"{result.name}: {result.detail}" for result in report.results if not result.passed
        ]
        if failed:
            pytest.fail("; ".join(failed), pytrace=False)

    return test
