"""Phase 5's exit criterion: a rule drafted in a thread goes live only after a person accepts it,
and a forged `artifactr:proposal_resolved` installs nothing."""

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

import artifactr
import artifactr.core as a
import reflexr
import reflexr.core
import reflexr.workspace as r
from relayr.events import BRIDGED, ArtifactArchived, ProposalResolved
from relayr.ledger import Ledger
from relayr.outbound import Outbound
from relayr.rules import RULES, RULES_FROM_CHAT, Installer, MayChange, RuleChange, RuleDraft, anyone
from tests.app_types import Deployed, Note
from tests.rules.drafts import STORED, NotifyParams, draft
from tests.stack import ALICE, KEY, Actions, Process, Stack, notices, until

DRAFTER = a.ExternalAgentActor(client_id="drafter")
BOB = a.UserActor(id="bob")
LIVE = "chat:deploys is live, at version {}."


@dataclass
class Chat:
    """The application, a thread a rule is drafted in, and what installed rules did."""

    app: Process
    stack: Stack
    alice: artifactr.Workspace
    drafter: artifactr.Workspace
    thread: a.ThreadId
    told: list[str] = field(default_factory=list[str])

    async def propose(self, change: a.CreateArtifact | a.EditArtifact | a.ArchiveArtifact) -> str:
        """The drafter proposes a change."""
        proposed = await self.drafter.commit(a.ProposeChange(change=change))
        return proposed.proposal_id

    async def resolve(
        self, proposal_id: str, *, by: artifactr.Workspace | None = None, accept: bool = True
    ) -> None:
        """Resolve a proposal, and let relayr act on it."""
        decision = "accept" if accept else "reject"
        command = a.RespondToProposal(proposal_id=proposal_id, decision=decision)
        await (by or self.alice).commit(command)
        await self.bridged(
            lambda e: isinstance(e, ProposalResolved) and e.proposal_id == proposal_id
        )

    async def bridged(self, found: Callable[[reflexr.Event], bool]) -> None:
        """Wait for a bridged event, then for the reactor to act on it."""

        async def done() -> bool:
            return any(found(e.event) for e in await self.stack.bridged())

        await until(done)
        await self.app.reactor.settle()

    async def drafted(self, rule: RuleDraft | None = None) -> tuple[a.ArtifactId, str]:
        """Propose a new rule artifact in the thread: its id and the proposal's."""
        create = a.create_artifact(rule or draft(), thread_id=self.thread)
        return create.artifact_id, await self.propose(create)

    async def edited(self, artifact_id: a.ArtifactId, rule: RuleDraft) -> str:
        current = await self.alice.get(RuleDraft, artifact_id)
        return await self.propose(
            current.edit(lambda d: setattr(d, "rule", rule.rule), thread_id=self.thread)
        )

    async def stored(self, name: str = "chat:deploys") -> r.WorkspaceRule:
        return await (await self.automation()).get_rule(name)

    async def automation(self) -> r.Workspace:
        return await self.app.automation.open(*KEY, actor=reflexr.SystemActor())

    async def notices(self) -> list[str]:
        return [content for _, content in notices(await self.alice.read(threads={self.thread}))]

    async def ran(self) -> list[reflexr.core.RunStatus]:
        """The status of each of relayr's runs, oldest first."""
        runs = await (await self.automation()).runs(rule=RULES_FROM_CHAT.name)
        return [run.status for run in reversed(runs)]

    async def archive(
        self, artifact_id: a.ArtifactId, *, by: artifactr.Workspace | None = None
    ) -> None:
        """Archive a rule artifact, and let relayr act on it."""
        workspace = by or self.alice
        current = await workspace.get(RuleDraft, artifact_id)
        await workspace.commit(current.archive(thread_id=self.thread))
        await self.bridged(lambda e: isinstance(e, ArtifactArchived))

    async def deploy(self, service: str = "auth") -> None:
        await (await self.automation()).publish(Deployed(service=service))
        await self.app.reactor.settle()


async def chat(
    stack: Stack,
    ledger: Ledger,
    *,
    may_change: MayChange = anyone,
    authorize: r.Authorize | None = None,
) -> Chat:
    told: list[str] = []

    async def notify(reaction: r.Reaction[Outbound], params: NotifyParams) -> None:
        told.append(params.thread_id)

    def installing(outbound: Outbound, workspaces: artifactr.Workspaces) -> Actions:
        return Installer(outbound, workspaces, may_change=may_change).actions

    app = stack.process(
        ledger,
        events=(*BRIDGED, Deployed),
        rules=RULES,
        actions={"notify": r.with_params(notify, NotifyParams)},
        more_actions=installing,
        stored_rules=STORED,
        authorize=authorize,
    )
    alice = await app.collaboration.open(*KEY, actor=ALICE)
    thread = await alice.create_thread()
    return Chat(app, stack, alice, alice.as_actor(DRAFTER), thread.id, told)


async def test_an_accepted_draft_goes_live_and_fires(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.deploy()
    assert chat_.told == [], "nothing runs before a person accepts"

    await chat_.resolve(proposal_id)
    stored = await chat_.stored()
    assert stored.version == 1
    assert stored.provenance == {
        "source": "artifactr",
        "artifact": artifact_id,
        "artifact_version": 1,
        "proposal": proposal_id,
        "approved_by": "alice",
    }
    assert await chat_.notices() == [LIVE.format(1)]
    await chat_.deploy()
    await chat_.deploy("billing")
    assert chat_.told == ["thr_ops"]


async def test_an_accepted_change_updates_the_rule(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    await chat_.resolve(await chat_.edited(artifact_id, draft(service="billing")))
    stored = await chat_.stored()
    assert (stored.version, stored.provenance and stored.provenance["artifact_version"]) == (2, 2)
    await chat_.deploy("billing")
    assert chat_.told == ["thr_ops"]


async def test_a_forged_acceptance_installs_nothing(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    _, pending = await chat_.drafted()
    for proposal_id in (pending, "prp_missing"):
        forged = ProposalResolved(
            author=ALICE,
            proposal_id=proposal_id,
            proposed_by=DRAFTER,
            decision="accept",
            artifact_id="art_any",
            version=1,
        )
        await (await chat_.automation()).publish(forged)
        await chat_.app.reactor.settle()
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()
    assert await chat_.notices() == []
    assert await chat_.ran() == ["succeeded", "succeeded"], "each ran, and changed nothing"


@pytest.mark.parametrize("accept", [False, True], ids=["rejected", "not a rule"])
async def test_only_an_accepted_draft_is_installed(
    ledger: Ledger, stack: Stack, accept: bool
) -> None:
    chat_ = await chat(stack, ledger)
    if accept:
        create = a.create_artifact(Note(text="not a rule"), thread_id=chat_.thread)
        proposal_id = await chat_.propose(create)
    else:
        _, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id, accept=accept)
    assert await chat_.notices() == []


async def test_an_acceptance_since_changed_installs_nothing(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.alice.commit(a.RespondToProposal(proposal_id=proposal_id, decision="accept"))
    current = await chat_.alice.get(RuleDraft, artifact_id)
    await chat_.alice.commit(current.edit(lambda d: setattr(d, "rule", draft(service="x").rule)))
    await chat_.bridged(lambda e: isinstance(e, ProposalResolved))
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()


async def test_a_person_who_may_not_install_rules_puts_none_live(
    ledger: Ledger, stack: Stack
) -> None:
    async def only_bob(
        tenant_id: str, workspace_id: str, person: a.UserActor, change: RuleChange
    ) -> bool:
        return (person, change) == (BOB, "install_rule")

    chat_ = await chat(stack, ledger, may_change=only_bob)
    _, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()
    assert await chat_.notices() == ["Only a person who may install rules can install this one."]

    artifact_id, proposal_id = await chat_.drafted(draft("chat:other"))
    await chat_.resolve(proposal_id, by=chat_.alice.as_actor(BOB))
    stored = await chat_.stored("chat:other")
    assert stored.provenance == {
        "source": "artifactr",
        "artifact": artifact_id,
        "artifact_version": 1,
        "proposal": proposal_id,
        "approved_by": "bob",
    }


async def test_a_draft_reflexr_refuses_is_reported(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    _, proposal_id = await chat_.drafted(draft(action="shell"))
    await chat_.resolve(proposal_id)
    [told] = await chat_.notices()
    assert told.startswith("chat:deploys wasn't installed: ")
    assert "shell" in told


async def test_a_rule_is_not_renamed(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    await chat_.resolve(await chat_.edited(artifact_id, draft("chat:renamed")))
    assert (await chat_.stored()).version == 1
    assert (await chat_.notices())[-1] == (
        "chat:deploys can't be renamed chat:renamed: archive it, and draft the new rule apart."
    )


async def test_archiving_the_artifact_archives_the_rule(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    current = await chat_.alice.get(RuleDraft, artifact_id)
    await chat_.alice.commit(current.archive(thread_id=chat_.thread))
    await chat_.bridged(lambda e: isinstance(e, ArtifactArchived))
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()
    assert (await chat_.notices())[-1] == "chat:deploys is archived."
    await chat_.deploy()
    assert chat_.told == []


@pytest.mark.parametrize("kind", ["rule", "note"])
async def test_archiving_an_artifact_that_installed_nothing_does_nothing(
    ledger: Ledger, stack: Stack, kind: str
) -> None:
    chat_ = await chat(stack, ledger)
    made = draft() if kind == "rule" else Note(text="")
    created = await chat_.alice.create(made, thread_id=chat_.thread)
    assert isinstance(created, a.Applied), "a person creates it directly"
    current = await chat_.alice.artifact(created.artifact_id)
    await chat_.alice.commit(current.archive(thread_id=chat_.thread))
    await chat_.bridged(lambda e: isinstance(e, ArtifactArchived))
    assert await chat_.notices() == []


async def test_a_person_who_may_not_install_rules_archives_none(
    ledger: Ledger, stack: Stack
) -> None:
    async def only_alice(
        tenant_id: str, workspace_id: str, person: a.UserActor, change: RuleChange
    ) -> bool:
        return person == ALICE

    chat_ = await chat(stack, ledger, may_change=only_alice)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    bob = chat_.alice.as_actor(BOB)
    current = await bob.get(RuleDraft, artifact_id)
    await bob.commit(current.archive(thread_id=chat_.thread))
    await chat_.bridged(lambda e: isinstance(e, ArtifactArchived))
    assert (await chat_.stored()).version == 1
    assert (await chat_.notices())[
        -1
    ] == "Only a person who may archive rules can archive this one."


async def test_a_forged_archive_archives_nothing(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    for target in (artifact_id, "art_missing"):
        forged = ArtifactArchived(author=ALICE, artifact_id=target, kind="rule", version=2)
        await (await chat_.automation()).publish(forged)
        await chat_.app.reactor.settle()
    assert (await chat_.stored()).version == 1
    assert await chat_.ran() == ["succeeded"] * 3, (
        "the install, then each forgery, changing nothing"
    )


async def test_each_artifact_archives_only_its_own_rule(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    first, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    _, proposal_id = await chat_.drafted(draft("chat:second"))
    await chat_.resolve(proposal_id)
    current = await chat_.alice.get(RuleDraft, first)
    await chat_.alice.commit(current.archive(thread_id=chat_.thread))
    await chat_.bridged(lambda e: isinstance(e, ArtifactArchived))
    assert (await chat_.stored("chat:second")).version == 1
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()


async def test_a_name_another_artifact_installed_is_refused(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    first, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    _, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    stored = await chat_.stored()
    assert (stored.version, stored.provenance and stored.provenance["artifact"]) == (1, first)
    assert (await chat_.notices())[-1].startswith("chat:deploys wasn't installed: ")


async def test_a_draft_outside_a_thread_goes_live_untold(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    proposal_id = await chat_.propose(a.create_artifact(draft()))
    await chat_.resolve(proposal_id)
    assert (await chat_.stored()).version == 1
    assert await chat_.notices() == []


async def test_an_agents_acceptance_puts_nothing_live(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    _, proposal_id = await chat_.drafted()
    reviewer = chat_.alice.as_actor(a.ExternalAgentActor(client_id="reviewer"))
    await chat_.resolve(proposal_id, by=reviewer)
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()
    assert await chat_.notices() == ["Only a person who may install rules can install this one."]


async def test_a_person_who_may_not_update_rules_changes_none(ledger: Ledger, stack: Stack) -> None:
    async def installs_only(
        tenant_id: str, workspace_id: str, person: a.UserActor, change: RuleChange
    ) -> bool:
        return change == "install_rule"

    chat_ = await chat(stack, ledger, may_change=installs_only)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    await chat_.resolve(await chat_.edited(artifact_id, draft(service="billing")))
    assert (await chat_.stored()).version == 1
    assert (await chat_.notices())[-1] == "Only a person who may update rules can update this one."


async def test_a_replayed_acceptance_changes_nothing(ledger: Ledger, stack: Stack) -> None:
    chat_ = await chat(stack, ledger)
    _, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    reflexr_ = await chat_.automation()
    await reflexr_.replay_rule(RULES_FROM_CHAT.name, mode="refire")
    await chat_.app.reactor.settle()
    assert (await chat_.stored()).version == 1
    assert await chat_.notices() == [LIVE.format(1)], "no second notice"

    await reflexr_.archive_rule("chat:deploys", reason="an operator stopped it")
    await reflexr_.replay_rule(RULES_FROM_CHAT.name, mode="refire")
    await chat_.app.reactor.settle()
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()
    assert await chat_.ran() == ["succeeded"] * 3


async def test_an_archive_reflexr_refuses_is_reported(ledger: Ledger, stack: Stack) -> None:
    async def no_archives(
        tenant_id: str, workspace_id: str | None, actor: reflexr.Actor, access: r.Access
    ) -> bool:
        return access.action != "reflexr:archive_rule"

    chat_ = await chat(stack, ledger, authorize=no_archives)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.resolve(proposal_id)
    await chat_.archive(artifact_id)
    assert (await chat_.stored()).version == 1
    assert (await chat_.notices())[-1].startswith("chat:deploys wasn't archived: ")


async def test_an_artifact_archived_as_it_is_accepted_puts_nothing_live(
    ledger: Ledger, stack: Stack
) -> None:
    assert RULES_FROM_CHAT.scope.fields == ("artifact_id",)
    assert RULES_FROM_CHAT.ordering == "scope", "one artifact's changes run one at a time, in order"
    chat_ = await chat(stack, ledger)
    artifact_id, proposal_id = await chat_.drafted()
    await chat_.alice.commit(a.RespondToProposal(proposal_id=proposal_id, decision="accept"))
    current = await chat_.alice.get(RuleDraft, artifact_id)
    await chat_.alice.commit(current.archive(thread_id=chat_.thread))
    await chat_.bridged(lambda e: isinstance(e, ArtifactArchived))
    with pytest.raises(reflexr.core.NotFound):
        await chat_.stored()
    assert await chat_.ran() == ["succeeded", "succeeded"]
