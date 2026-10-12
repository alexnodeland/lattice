"""What the rules-from-chat tests share: stored rules' configuration, and a draft."""

from datetime import timedelta

from pydantic import BaseModel

import reflexr
import reflexr.core
from relayr.rules import RuleDraft
from tests.app_types import Deployed


class NotifyParams(BaseModel):
    thread_id: str


STORED = reflexr.core.StoredRules(actions={"notify": NotifyParams}, namespaces={"chat"})


def draft(
    name: str = "chat:deploys", *, service: str = "auth", action: str = "notify"
) -> RuleDraft:
    """A rule that tells a thread of each deploy of a service."""
    when = reflexr.on(Deployed).where(reflexr.F.service.eq(service))
    rule = reflexr.Rule(
        name=name,
        when=when.at_most(10, per=timedelta(hours=1)),
        then=reflexr.run(action, thread_id="thr_ops"),
        timeout=timedelta(minutes=1),
        ordering="none",
    )
    return RuleDraft(rule=rule)
