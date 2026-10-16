"""The record of an operator opening the tools: who, and what kind of thing they asked for.

Langfuse and Grafana aren't tenant-scoped, and what they show, what people and models said, isn't
behind portalr's gates for traces and logs. So each time portalr makes an operator's links into
them, it logs one structured line on ``portalr.access``, as grantr logs each audit entry
(``grantr.audit``): the operator, the kinds of id they gave, the tenant if they asked for one, and
the tools a link was made for. It never holds a trace's, a session's or a run's id, a URL, or a
key. It has no ``tenant_id``, so it is no tenant's to read in Logs, and it is written only once the
caller is known to be an operator and the ids are known to be good: a refusal logs nothing. How
long it lasts is the deployment's log retention, in Loki; a durable record would be grantr's
(portalr ADR-0035).
"""

import json
import logging
from collections.abc import Sequence
from typing import Final

from grantr.core import Subject

ACCESS_LOG: Final = logging.getLogger("portalr.access")
"""Where an operator's opening of the tools is recorded."""


def record_links(
    by: Subject, *, kinds: Sequence[str], tenant: str | None, tools: Sequence[str]
) -> None:
    """Record that ``by`` was given links, for these kinds of id, into these tools."""
    ACCESS_LOG.info(
        "%s",
        json.dumps(
            {
                "event": "deployment_links",
                "by": by.model_dump(mode="json"),
                "kinds": list(kinds),
                "tenant": tenant,
                "tools": list(tools),
            },
            sort_keys=True,
        ),
    )
