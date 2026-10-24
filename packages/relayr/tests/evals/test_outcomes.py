"""Phase 6: how people resolve a rule's proposals is feedback on the run that proposed."""

from dataclasses import dataclass

import pytest

import artifactr
import artifactr.core as a
import reflexr
import reflexr.core
import reflexr.workspace as r
from artifactr.workspace import Scope
from relayr.evals import RULES, Outcomes, ProposalRates, proposal_rates
from relayr.evals.outcomes import _how
from relayr.events import ArtifactCreated, ProposalResolved
from relayr.ledger import Cause, Ledger
from relayr.outbound import Outbound, rule_actor
from tests.app_types import Note, Range
from tests.stack import ALICE, KEY, Actions, Process, Stack, until

PROPOSE = reflexr.Rule(
    name="app:propose",
    when=reflexr.on(ArtifactCreated).where(reflexr.F.author.kind.eq("user")),
    then=reflexr.run("propose"),
)


@dataclass
class Scene:
    app: Process
    stack: Stack
    alice: artifactr.Workspace
    change: str

    async def proposed(self) -> a.Proposal:
        """An artifact Alice writes, and the rule's proposal to change it."""
        if self.change == "range":
            await self.alice.create(Range(), artifact_id="art_range")
        else:
            await self.alice.create(Note(text="draft"), artifact_id="art_note")

        async def made() -> bool:
            await self.app.reactor.settle()
            return bool(await self.alice.proposals())

        await until(made)
        [proposal] = await self.alice.proposals()
        return proposal

    async def resolve(
        self, proposal: a.Proposal, *, accept: bool, changes: a.Patch | None = None
    ) -> None:
        decision = "accept" if accept else "reject"
        command = a.RespondToProposal(proposal_id=proposal.id, decision=decision, changes=changes)
        await self.alice.commit(command)

        def resolved(so_far: list[reflexr.Envelope]) -> bool:
            event = so_far[-1].event
            return isinstance(event, ProposalResolved) and event.proposal_id == proposal.id

        await self.stack.until_bridged(resolved)
        await self.app.reactor.settle()

    async def rates(self) -> dict[str, ProposalRates]:
        return await proposal_rates(
            await self.app.automation.open(*KEY, actor=reflexr.SystemActor())
        )


async def scene(stack: Stack, ledger: Ledger, change: str = "edit") -> Scene:
    async def propose(reaction: r.Reaction[Outbound]) -> None:
        acting = reaction.deps.acting(reaction)
        if change == "edit":
            await acting.edit("art_note", "/text", "proposed", rationale="clearer")
        elif change == "range":
            await acting.edit("art_range", "/low", 5)
        elif change == "create":
            await acting.create(Note(text="new"))
        else:
            await acting.archive("art_note")

    def scoring(outbound: Outbound, workspaces: artifactr.Workspaces) -> Actions:
        return Outcomes(workspaces, ledger).actions

    app = stack.process(
        ledger, rules=[PROPOSE, *RULES], actions={"propose": propose}, more_actions=scoring
    )
    return Scene(app, stack, await app.collaboration.open(*KEY, actor=ALICE), change)


def text(value: str) -> a.Patch:
    return a.JsonPatch(ops=({"op": "replace", "path": "/text", "value": value},))


@pytest.mark.parametrize(
    ("accept", "changes", "expected"),
    [
        (True, None, ProposalRates(accepted=1)),
        (True, text("mine"), ProposalRates(edited=1)),
        (True, text("proposed"), ProposalRates(accepted=1)),
        (False, None, ProposalRates(rejected=1)),
    ],
    ids=["as proposed", "edited", "changes that change nothing", "rejected"],
)
async def test_a_resolved_proposal_scores_the_run_that_made_it(
    ledger: Ledger, stack: Stack, accept: bool, changes: a.Patch | None, expected: ProposalRates
) -> None:
    scene_ = await scene(stack, ledger)
    await scene_.resolve(await scene_.proposed(), accept=accept, changes=changes)
    assert await scene_.rates() == {"app:propose": expected}


@pytest.mark.parametrize(
    ("change", "changes", "expected"),
    [
        ("create", None, ProposalRates(accepted=1)),
        ("create", text("mine"), ProposalRates(edited=1)),
        ("archive", None, ProposalRates(accepted=1)),
    ],
    ids=["a create", "an edited create", "an archive"],
)
async def test_every_kind_of_proposal_is_scored(
    ledger: Ledger, stack: Stack, change: str, changes: a.Patch | None, expected: ProposalRates
) -> None:
    scene_ = await scene(stack, ledger, change)
    await scene_.resolve(await scene_.proposed(), accept=True, changes=changes)
    assert await scene_.rates() == {"app:propose": expected}


class Thumbs(reflexr.Feedback, name="thumbs", targets={"run"}):
    up: bool


async def test_an_outcome_is_scored_once(ledger: Ledger, stack: Stack) -> None:
    scene_ = await scene(stack, ledger)
    proposal = await scene_.proposed()
    automation = await scene_.app.automation.open(*KEY, actor=reflexr.SystemActor())
    [proposing] = await automation.runs(rule="app:propose")
    person = automation.as_actor(reflexr.UserActor(id="alice"))
    await person.give_feedback(Thumbs(up=True), on=reflexr.core.RunTarget(run_id=proposing.id))
    await scene_.resolve(proposal, accept=True)
    await automation.replay_rule("relayr:proposal-outcome", mode="refire")
    await scene_.app.reactor.settle()
    assert await scene_.rates() == {"app:propose": ProposalRates(accepted=1)}


async def test_only_a_rules_traced_proposal_is_scored(ledger: Ledger, stack: Stack) -> None:
    scene_ = await scene(stack, ledger)
    await scene_.alice.create(Note(text="x"), artifact_id="art_other")
    impostor = scene_.alice.as_actor(a.ExternalAgentActor(client_id="reflexr:app:fake"))
    person = scene_.alice.as_actor(a.ExternalAgentActor(client_id="client"))
    for proposer in (impostor, person):
        current = await proposer.artifact("art_other")
        edit = a.EditArtifact(
            artifact_id="art_other", base_version=current.version, patch=text("y")
        )
        proposed = await proposer.commit(a.ProposeChange(change=edit))
        await scene_.resolve(await scene_.alice.proposal(proposed.proposal_id), accept=False)
    forged = ProposalResolved(
        author=ALICE,
        proposal_id="prp_missing",
        proposed_by=a.ExternalAgentActor(client_id="reflexr:app:fake"),
        decision="accept",
        artifact_id="art_other",
    )
    automation = await scene_.app.automation.open(*KEY, actor=reflexr.SystemActor())
    await automation.publish(forged)
    await scene_.app.reactor.settle()
    assert await scene_.rates() == {}


def test_rates_are_shares_of_what_was_resolved() -> None:
    rates = ProposalRates(accepted=1, edited=1, rejected=2)
    assert (rates.acceptance, rates.edit_rate) == (0.5, 0.5)
    assert (ProposalRates().acceptance, ProposalRates().edit_rate) == (0.0, 0.0)


async def test_an_edit_accepted_after_another_is_scored_against_the_version_it_met(
    ledger: Ledger, stack: Stack
) -> None:
    scene_ = await scene(stack, ledger)
    proposal = await scene_.proposed()
    current = await scene_.alice.get(Note, "art_note")
    await scene_.alice.commit(current.edit(lambda note: setattr(note, "text", "meanwhile")))
    await scene_.resolve(proposal, accept=True)
    assert await scene_.rates() == {"app:propose": ProposalRates(accepted=1)}


async def test_a_proposal_valid_only_with_the_persons_changes_is_edited(
    ledger: Ledger, stack: Stack
) -> None:
    scene_ = await scene(stack, ledger, "range")
    proposal = await scene_.proposed()
    current = await scene_.alice.get(Range, "art_range")
    await scene_.alice.commit(current.edit(lambda bounds: setattr(bounds, "high", 3)))
    fix = a.JsonPatch(ops=({"op": "replace", "path": "/high", "value": 8},))
    await scene_.resolve(proposal, accept=True, changes=fix)
    assert await scene_.rates() == {"app:propose": ProposalRates(edited=1)}


async def test_an_edit_is_scored_against_the_kept_version_before_it() -> None:
    storage = artifactr.InMemoryStorage()
    ws = await artifactr.Workspaces(storage).open(*KEY, actor=ALICE)
    await ws.create(Note(text="draft"), artifact_id="art_note")
    note = await ws.get(Note, "art_note")
    await ws.commit(note.edit(lambda n: setattr(n, "text", "second")))  # 2
    agent = a.AgentActor(thread_id="t1", run_id="r1", name="assistant", on_behalf_of=ALICE)
    change = a.EditArtifact(artifact_id="art_note", base_version=2, patch=text("proposed"))
    await ws.as_actor(agent).commit(a.ProposeChange(change=change))
    [proposal] = await ws.proposals()
    await ws.commit(a.RespondToProposal(proposal_id=proposal.id, decision="accept"))  # 3
    await ws.commit((await ws.get(Note, "art_note")).edit(lambda n: setattr(n, "text", "x")))
    assert await storage.drop_revisions(Scope(*KEY), "art_note", [2]) == 1
    assert await _how(ws, proposal) == "accepted", "against version 1, the kept one before"


async def test_a_second_resolution_scores_nothing_more(ledger: Ledger, stack: Stack) -> None:
    scene_ = await scene(stack, ledger)
    proposal = await scene_.proposed()
    await scene_.resolve(proposal, accept=True)
    again = ProposalResolved(
        author=ALICE,
        proposal_id=proposal.id,
        proposed_by=proposal.proposed_by,
        decision="reject",
        artifact_id="art_note",
    )
    automation = await scene_.app.automation.open(*KEY, actor=reflexr.SystemActor())
    await automation.publish(again)
    await scene_.app.reactor.settle()
    assert await scene_.rates() == {"app:propose": ProposalRates(accepted=1)}


async def test_a_squatted_proposal_id_scores_no_rules_run(ledger: Ledger, stack: Stack) -> None:
    scene_ = await scene(stack, ledger)
    proposal = await scene_.proposed()
    automation = await scene_.app.automation.open(*KEY, actor=reflexr.SystemActor())
    [proposing] = await automation.runs(rule="app:propose")
    cause = Cause(
        correlation_id=proposing.correlation_id,
        firing_id=proposing.causation.firing_id,
        run_id=proposing.causation.run_id,
        depth=proposing.causation.depth,
    )
    await ledger.record_cause(KEY, "proposal", "prp_squat", cause)
    other = scene_.alice.as_actor(rule_actor("app:other"))
    current = await other.artifact("art_note")
    edit = a.EditArtifact(artifact_id="art_note", base_version=current.version, patch=text("x"))
    await other.commit(a.ProposeChange(change=edit, proposal_id="prp_squat"))
    await scene_.resolve(await scene_.alice.proposal("prp_squat"), accept=False)
    await scene_.resolve(proposal, accept=True)
    assert await scene_.rates() == {"app:propose": ProposalRates(accepted=1)}
