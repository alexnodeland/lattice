"""Measures from the logs: rules from chat from draft to survival, and an artifact's history."""

from datetime import timedelta

import artifactr
import artifactr.core as a
import reflexr
import reflexr.core
import reflexr.workspace as r
from evalr.measures import measure_rewrites
from relayr.evals import RuleConversion, history, rule_conversion
from relayr.rules import RULES_FROM_CHAT
from tests.app_types import Deployed, Note
from tests.clock import FakeClock
from tests.rules.drafts import STORED, draft
from tests.stack import ALICE, KEY

RELAYR = reflexr.core.AgentActor(rule=RULES_FROM_CHAT.name, run_id="fir_1", name="rules-from-chat")
OPERATOR = reflexr.UserActor(id="ops")


async def test_rules_from_chat_are_followed_from_draft_to_survival(clock: FakeClock) -> None:
    collaboration = artifactr.Workspaces(artifactr.InMemoryStorage())
    alice = await collaboration.open(*KEY, actor=ALICE)
    drafter = alice.as_actor(a.ExternalAgentActor(client_id="drafter"))
    proposals = []
    for name in ("chat:one", "chat:two", "chat:three", "chat:four"):
        create = a.create_artifact(draft(name))
        proposals.append((await drafter.commit(a.ProposeChange(change=create))).proposal_id)
    await drafter.commit(a.ProposeChange(change=a.create_artifact(Note(text="not a rule"))))
    for proposal_id in proposals[:3]:
        await alice.commit(a.RespondToProposal(proposal_id=proposal_id, decision="accept"))

    workspaces = r.Workspaces(
        r.InMemoryStorage(clock=clock), events=[Deployed], stored_rules=STORED
    )
    automation = await workspaces.open(*KEY, actor=OPERATOR)
    installer = automation.as_actor(RELAYR)
    await automation.install_rule(draft("chat:one").rule)  # an operator's, archived before
    await automation.archive_rule("chat:one")  # relayr ever installed it: no count against it
    await installer.install_rule(draft("chat:one").rule)
    await installer.install_rule(draft("chat:two").rule)
    await automation.install_rule(draft("chat:direct").rule)  # not from chat
    clock.advance(timedelta(days=31))
    await installer.install_rule(draft("chat:three").rule)  # too recent to count
    await automation.archive_rule("chat:two", reason="an operator stopped it")

    later = clock.now + timedelta(seconds=1)
    assert (await rule_conversion(alice, automation, now=clock.now)).installed == 2, "before now"
    measured = await rule_conversion(alice, automation, now=later)
    assert measured == RuleConversion(proposed=4, accepted=3, installed=3, eligible=2, survived=1)
    assert measured.survival == 0.5
    empty = await rule_conversion(alice, automation, now=later, survival=timedelta(days=90))
    assert (empty.eligible, empty.survival) == (0, 0.0)


async def test_an_artifacts_history_is_read_for_evalrs_measures() -> None:
    collaboration = artifactr.Workspaces(artifactr.InMemoryStorage())
    alice = await collaboration.open(*KEY, actor=ALICE)
    rule = alice.as_actor(a.ExternalAgentActor(client_id="reflexr:app:timeline"))
    created = await rule.create(Note(text="what the rule wrote"), artifact_id="art_t")
    assert isinstance(created, a.Applied)
    current = await alice.get(Note, "art_t")
    await alice.commit(
        current.edit(
            lambda note: setattr(
                note, "text", "Rolled back the deploy at noon, and paged the on-call person."
            )
        )
    )
    edited = await alice.get(Note, "art_t")
    proposing = await rule.commit(
        a.ProposeChange(change=edited.edit(lambda note: setattr(note, "text", "The rule's take.")))
    )
    await alice.commit(a.RespondToProposal(proposal_id=proposing.proposal_id, decision="accept"))
    for actor, said in (
        (a.SystemActor(), "Tidied."),
        (a.ExternalAgentActor(client_id="mcp", on_behalf_of=ALICE), "Alice, through her client."),
    ):
        edited = await alice.as_actor(actor).get(Note, "art_t")
        await alice.as_actor(actor).commit(
            edited.edit(lambda note, t=said: setattr(note, "text", t))
        )
    edited = await alice.get(Note, "art_t")
    await alice.commit(edited.archive())
    found = await history(alice, "art_t")
    assert [v.role for v in found.revisions] == ["agent", "person", "agent", "system", "person"]
    assert "Rolled" in found.revisions[1].text, "an accepted proposal's version is its proposer's"
    rewrites = measure_rewrites(found, window=timedelta(hours=1))
    assert (rewrites.agent_revisions, rewrites.rewritten) == (2, 2)
