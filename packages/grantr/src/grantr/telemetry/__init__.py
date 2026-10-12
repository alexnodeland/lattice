"""grantr's telemetry, through the OpenTelemetry API only.

The API is the port, as in the libraries: grantr records under the ``grantr`` scope and never
configures the SDK, so with none configured, recording is a no-op.

- **Checks are counted** in ``grantr.checks``, by action, outcome and, for a refusal, its
  reason. An action in no catalog is counted as ``unknown``, so the actions are the catalogs'
  and the reasons :data:`Reason`'s, and the counter's attributes are bounded however callers
  ask. Tenants and subjects are never metric attributes.
- **A slow check is a span,** ``grantr.check``, recorded once it is over the threshold, from its
  start, with the action as asked: a check that is fast leaves no span.
- **Every audit entry is logged,** at the info level on the ``grantr.audit`` logger, so the
  stack's logs hold a copy of the audit log.
"""

import logging
from datetime import timedelta
from importlib.metadata import version
from typing import Final, Literal

from opentelemetry import metrics, trace
from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import TracerProvider

from grantr.core import AuditEntry, TenantId

SCOPE: Final = "grantr"
"""The instrumentation scope of grantr's spans and metrics."""

CHECKS: Final = "grantr.checks"
"""The counter of checks."""

CHECK_SPAN: Final = "grantr.check"
"""The span of a slow check."""

ACTION: Final = "grantr.action"
OUTCOME: Final = "grantr.outcome"
REASON: Final = "grantr.reason"
TENANT_ID: Final = "grantr.tenant.id"

UNKNOWN: Final = "unknown"
"""The action a check of an action in no catalog is counted under."""

SLOW_CHECK: Final = timedelta(milliseconds=50)
"""How long a check takes before it is recorded as a span, by default."""

type Reason = Literal["unknown_action", "no_grant", "store_unreadable"]
"""Why a check was refused."""

audit_log = logging.getLogger("grantr.audit")
"""Where each audit entry is logged."""


class Telemetry:
    """The tracer and meter :class:`~grantr.grants.Grants` records with.

    Args:
        tracer_provider: Where spans go. Defaults to the global tracer provider.
        meter_provider: Where metrics go. Defaults to the global meter provider.
        slow_check: How long a check takes before it is recorded as a span.
    """

    def __init__(
        self,
        *,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        slow_check: timedelta = SLOW_CHECK,
    ) -> None:
        tracer_provider = tracer_provider or trace.get_tracer_provider()
        meter_provider = meter_provider or metrics.get_meter_provider()
        self._tracer = tracer_provider.get_tracer(SCOPE, version("grantr"))
        self._checks = meter_provider.get_meter(SCOPE, version("grantr")).create_counter(
            CHECKS, "{check}", "Checks, by action, outcome and the reason for a refusal"
        )
        self._slow_ns = int(slow_check.total_seconds() * 1e9)

    def checked(
        self, tenant: TenantId, action: str, refused: Reason | None, *, start: int, end: int
    ) -> None:
        """Count a check, and record it as a span if it was slow.

        Args:
            tenant: The check's tenant, which only the span carries.
            action: The action checked.
            refused: Why it was refused, or None if it was allowed.
            start: When it started, in nanoseconds since the epoch.
            end: When it ended, in the same clock.
        """
        counted = UNKNOWN if refused == "unknown_action" else action
        attributes = {ACTION: counted, OUTCOME: "refused" if refused else "allowed"}
        if refused:
            attributes[REASON] = refused
        self._checks.add(1, attributes)
        if end - start >= self._slow_ns:
            span = self._tracer.start_span(
                CHECK_SPAN,
                start_time=start,
                attributes={**attributes, ACTION: action, TENANT_ID: tenant},
            )
            span.end(end_time=end)

    def audited(self, entry: AuditEntry) -> None:
        """Log an audit entry, once its change has committed."""
        audit_log.info("%s", entry.model_dump_json())
