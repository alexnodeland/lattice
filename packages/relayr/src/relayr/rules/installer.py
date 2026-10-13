"""relayr's own rule, which puts the drafts people accept live in reflexr, and archives them.

`relayr:rules-from-chat` fires on an accepted proposal and on an archived `rule` artifact. It is
scoped by the artifact, so one artifact's acceptances and archive run one at a time, in the order
they happened. It never trusts the bridged event: it re-reads artifactr, as its rule's own
participant, and acts only on what artifactr's own record says.

- **The proposal was accepted**, and its artifact is a `rule`.
- **The artifact is still at the version the acceptance made**, or, for an archive, at the version
  that archived it. A later change acts for itself.
- **The person who accepted, or archived, may make the change**: install, update or archive the
  rule. They are the actor of the artifact's revision at that version, which artifactr records
  with the proposal it applied, and `may_change` says whether they may.

A forged event therefore changes nothing, and nor does an acceptance replayed after it was
installed.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, JsonValue

import artifactr
import artifactr.core as a
import reflexr.core
from reflexr import F, Rule, by, on, run
from reflexr.core import AnyFilter, Condition, RuleName
from reflexr.workspace import Action, Reaction, Workspace, WorkspaceRule
from relayr.events import ArtifactArchived, ProposalResolved
from relayr.outbound import Allowlist, Outbound, RunActions, rule_actor
from relayr.rules.drafts import RuleDraft

type RuleChange = Literal["install_rule", "update_rule", "archive_rule"]
"""A change to a stored rule, named as reflexr's action for it is, without its prefix."""

type MayChange = Callable[[str, str, a.UserActor, RuleChange], Awaitable[bool]]
"""Whether a person may make a change to stored rules in a tenant's workspace:
``(tenant, workspace, person, change)``."""


async def anyone(
    _tenant_id: str, _workspace_id: str, _person: a.UserActor, _change: RuleChange
) -> bool:
    """Let any person make any change: the choice for an application without access control."""
    return True


RULES_FROM_CHAT: Final = Rule(
    name="relayr:rules-from-chat",
    description="A proposal was accepted, or a rule artifact archived. Change its rule.",
    when=Condition(
        filter=AnyFilter(
            of=(
                on(ProposalResolved).where(F.decision.eq("accept")).filter,
                on(ArtifactArchived).where(F.kind.eq(RuleDraft.kind)).filter,
            )
        )
    ),
    scope=by(F.artifact_id),
    then=run("rules-from-chat"),
)

RULE_DRIFT: Final = Rule(
    name="relayr:rule-drift",
    description="A rule from chat changed in reflexr directly. Propose it to its artifact.",
    when=on("reflexr:rule_installed", "reflexr:rule_archived"),
    scope=by(F.rule),
    then=run("rule-drift"),
)

RULES: Final = [RULES_FROM_CHAT, RULE_DRIFT]
"""relayr's rules from chat, for the application's reflexr workspaces."""

ALLOWLISTS: Final[Mapping[RuleName, Allowlist]] = {RULE_DRIFT.name: Allowlist(threads="any")}
"""What relayr's rules from chat may do beyond proposals and notices in their chains' threads:
``relayr:rule-drift`` proposes in the thread its rule was drafted in, which its chain doesn't
hold. Give them to the outbound adapter with the application's own."""


class Installer:
    """The action of relayr's rule from chat. Register `actions` with the reactor.

    Args:
        outbound: The adapter the runs post their notices through.
        artifactr: The workspaces the runs re-read.
        may_change: Whether the person who accepted a draft, or archived it, may make the change
            to its rule. Pass [`anyone`][relayr.rules.anyone] for an application without access
            control.
    """

    def __init__(
        self, outbound: Outbound, artifactr: artifactr.Workspaces, *, may_change: MayChange
    ) -> None:
        self._outbound = outbound
        self._artifactr = artifactr
        self._may_change = may_change

    @property
    def actions(self) -> Mapping[str, Action[Any]]:
        """The rules' actions, by the names `RULES` run."""
        return {"rules-from-chat": self.act, "rule-drift": self.drift}

    async def act(self, reaction: Reaction[Any]) -> None:
        """Install or update the rule an accepted proposal drafted, or archive an artifact's."""
        [envelope] = reaction.events
        event = envelope.event
        if isinstance(event, ProposalResolved):
            await self._install(reaction, event)
        else:
            assert isinstance(event, ArtifactArchived), "the rule fires on nothing else"
            await self._archive(reaction, event)

    async def drift(self, reaction: Reaction[Any]) -> None:
        """Propose to its artifact a change made to a rule from chat in reflexr directly.

        A change relayr made itself, from an accepted draft, is in step already. A rule no draft
        installed has no artifact to keep in step.
        """
        [envelope] = reaction.events
        if isinstance(envelope.actor, reflexr.core.AgentActor) and (
            envelope.actor.rule == RULES_FROM_CHAT.name
        ):
            return
        event = envelope.event
        assert isinstance(event, reflexr.core.RuleInstalled | reflexr.core.RuleArchived)
        installs = await _installs(reaction.workspace, event.rule)
        if not installs:
            return
        origin = _Origin.model_validate(installs[-1].provenance)
        source = await self._open(reaction)
        # relayr installed the rule from this artifact, on this proposal: both exist.
        current = await source.get(RuleDraft, origin.artifact)
        if current.archived:
            return
        thread = (await source.proposal(origin.proposal)).thread_id
        acting = self._outbound.acting(reaction)
        who = envelope.actor.participant
        outside = f"{event.rule} was changed in reflexr by {who}, outside its artifact"
        if isinstance(event, reflexr.core.RuleArchived):
            why = f"{outside}: it was archived. Accept to archive the artifact too."
            await acting.archive(current.id, thread_id=thread, rationale=why)
        elif current.data.rule != Rule.model_validate(event.spec):
            why = f"{outside}, to version {event.version}. Accept to keep the two in step."
            await acting.edit(current.id, "/rule", event.spec, thread_id=thread, rationale=why)

    async def _install(self, reaction: Reaction[Any], resolved: ProposalResolved) -> None:
        source = await self._open(reaction)
        try:
            proposal = await source.proposal(resolved.proposal_id)
            revisions = await source.revisions(proposal.artifact_id)
        except a.NotFound:
            return
        revision = revisions[-1]
        if (
            proposal.status != "accepted"
            or revision.proposal_id != proposal.id
            or revision.kind != RuleDraft.kind
            or revision.archived
        ):
            return  # not accepted, or changed since, or not a rule
        target = reaction.workspace
        # artifactr validated the revision as a `RuleDraft` when it committed it.
        rule = RuleDraft.model_validate(revision.data).rule
        drafted = await _drafted_installs(target, revisions)
        if any(install.provenance.get("proposal") == proposal.id for install in drafted[rule.name]):
            return  # replayed: this acceptance was installed, and may be archived since
        acting = self._outbound.acting(reaction)
        thread = proposal.thread_id
        name = _rule_of(drafted, revision.artifact_id)
        if name is not None and name != rule.name:
            renamed = f"{name} can't be renamed {rule.name}"
            await _tell(acting, f"{renamed}: archive it, and draft the new rule apart.", thread)
            return
        installed = await _active(target, name)
        change: RuleChange = "install_rule" if installed is None else "update_rule"
        approver = await self._approver(reaction, acting, revision, change, thread)
        if approver is None:
            return
        provenance: dict[str, JsonValue] = {
            "source": "artifactr",
            "artifact": revision.artifact_id,
            "artifact_version": revision.version,
            "proposal": proposal.id,
            "approved_by": approver.id,
        }
        try:
            if installed is None:
                changed = await target.install_rule(rule, provenance=provenance)
            else:
                changed = await target.update_rule(
                    rule, expected_version=installed.version, provenance=provenance
                )
        except reflexr.core.Rejection as rejection:
            await _tell(acting, f"{rule.name} wasn't installed: {_why(rejection)}", thread)
            return
        # No duplicate reaches here: provenance names the proposal, and the replay check above
        # has looked for its install.
        live = f"{rule.name} is live, at version {changed.stored.version}."
        await _tell(acting, live, thread)

    async def _archive(self, reaction: Reaction[Any], archived: ArtifactArchived) -> None:
        source = await self._open(reaction)
        try:
            revisions = await source.revisions(archived.artifact_id)
        except a.NotFound:
            return
        revision = revisions[-1]
        if not revision.archived or revision.kind != RuleDraft.kind:
            return
        target = reaction.workspace
        drafted = await _drafted_installs(target, revisions)
        installed = await _active(target, _rule_of(drafted, archived.artifact_id))
        if installed is None:
            return
        acting = self._outbound.acting(reaction)
        thread = archived.thread_id
        if await self._approver(reaction, acting, revision, "archive_rule", thread) is None:
            return
        name = installed.rule.name
        reason = f"its artifact {archived.artifact_id} was archived"
        try:
            await target.archive_rule(name, expected_version=installed.version, reason=reason)
        except reflexr.core.Rejection as rejection:
            await _tell(acting, f"{name} wasn't archived: {_why(rejection)}", thread)
            return
        await _tell(acting, f"{name} is archived.", thread)

    async def _open(self, reaction: Reaction[Any]) -> artifactr.Workspace:
        """The run's workspace in artifactr, as its rule's own participant."""
        workspace = reaction.workspace
        actor = rule_actor(reaction.run.rule)
        return await self._artifactr.open(workspace.tenant_id, workspace.workspace_id, actor=actor)

    async def _approver(
        self,
        reaction: Reaction[Any],
        acting: RunActions,
        revision: a.Revision,
        change: RuleChange,
        thread_id: a.ThreadId | None,
    ) -> a.UserActor | None:
        """The person who made a revision, if they may make the change. Never an agent."""
        person = revision.actor
        workspace = reaction.workspace
        if isinstance(person, a.UserActor) and await self._may_change(
            workspace.tenant_id, workspace.workspace_id, person, change
        ):
            return person
        verb = change.removesuffix("_rule")
        await _tell(acting, f"Only a person who may {verb} rules can {verb} this one.", thread_id)
        return None


async def _installs(workspace: Workspace, rule: RuleName) -> list[reflexr.core.RuleInstalled]:
    """The installs of a rule relayr made from accepted drafts, oldest first, from its history.

    Each fact names the run that made it, so an install anyone else made, whatever provenance it
    claims, is not among them.
    """
    return [
        fact.event
        for fact in await workspace.rule_history(rule)
        if isinstance(fact.event, reflexr.core.RuleInstalled)
        and isinstance(fact.actor, reflexr.core.AgentActor)
        and fact.actor.rule == RULES_FROM_CHAT.name
    ]


class _Named(BaseModel):
    name: RuleName


class _Drafted(BaseModel):
    """Only the name of a revision's draft: an old revision need not parse as today's rule."""

    rule: _Named


async def _drafted_installs(
    workspace: Workspace, revisions: list[a.Revision]
) -> dict[RuleName, list[reflexr.core.RuleInstalled]]:
    """The installs relayr made of each rule a rule artifact's drafts named, by name.

    An installed rule can't be renamed, so this is almost always one name, but a draft may be
    renamed before anything installs it.
    """
    names = {_Drafted.model_validate(r.data).rule.name for r in revisions}
    return {name: await _installs(workspace, name) for name in sorted(names)}


def _rule_of(
    drafted: dict[RuleName, list[reflexr.core.RuleInstalled]], artifact_id: str
) -> RuleName | None:
    """The rule relayr installed from an artifact, among those its drafts named, if any.

    At most one name has installs from the artifact, since an installed rule can't be renamed;
    the names are in order, so the answer would be the same however many there were.
    """
    for name, installs in drafted.items():
        if any(i.provenance.get("artifact") == artifact_id for i in installs):
            return name
    return None


class _Origin(BaseModel):
    """Where relayr installed a rule from, as its provenance says."""

    artifact: str
    proposal: str


async def _active(workspace: Workspace, rule: RuleName | None) -> WorkspaceRule | None:
    """A stored rule, if it is active."""
    if rule is None:
        return None
    try:
        return await workspace.get_rule(rule)
    except reflexr.core.NotFound:
        return None


async def _tell(acting: RunActions, content: str, thread_id: a.ThreadId | None) -> None:
    """Post a notice in the draft's thread, if it has one."""
    if thread_id is not None:
        await acting.notice(content, thread_id=thread_id)


def _why(rejection: reflexr.core.Rejection) -> str:
    """What reflexr refused, with each problem it listed."""
    if isinstance(rejection, reflexr.core.ValidationFailed) and rejection.errors:
        return f"{rejection}: " + "; ".join(str(error) for error in rejection.errors)
    return str(rejection)
