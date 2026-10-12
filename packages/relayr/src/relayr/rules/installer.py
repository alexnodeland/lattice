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

from pydantic import JsonValue

import artifactr
import artifactr.core as a
import reflexr.core
from reflexr import F, Rule, by, on, run
from reflexr.core import AnyFilter, Condition
from reflexr.workspace import Action, Reaction, Workspace, WorkspaceRule
from relayr.events import ArtifactArchived, ProposalResolved
from relayr.outbound import Outbound, RunActions, rule_actor
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

RULES: Final = [RULES_FROM_CHAT]
"""relayr's rules from chat, for the application's reflexr workspaces."""


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
        """The rule's action, by the name `RULES_FROM_CHAT` runs."""
        return {"rules-from-chat": self.act}

    async def act(self, reaction: Reaction[Any]) -> None:
        """Install or update the rule an accepted proposal drafted, or archive an artifact's."""
        [envelope] = reaction.events
        event = envelope.event
        if isinstance(event, ProposalResolved):
            await self._install(reaction, event)
        else:
            assert isinstance(event, ArtifactArchived), "the rule fires on nothing else"
            await self._archive(reaction, event)

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
        if await _installed_by(target, proposal.id):
            return  # replayed: this acceptance was installed, and may be archived since
        acting = self._outbound.acting(reaction)
        thread = proposal.thread_id
        # artifactr validated the revision as a `RuleDraft` when it committed it.
        rule = RuleDraft.model_validate(revision.data).rule
        installed = await _installed_from(target, revision.artifact_id)
        if installed is not None and installed.rule.name != rule.name:
            renamed = f"{installed.rule.name} can't be renamed {rule.name}"
            await _tell(acting, f"{renamed}: archive it, and draft the new rule apart.", thread)
            return
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
        # No duplicate reaches here: provenance names the proposal, and `_installed_by` has
        # looked for its install.
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
        installed = await _installed_from(target, archived.artifact_id)
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


async def _installed_by(workspace: Workspace, proposal_id: a.ProposalId) -> bool:
    """Whether reflexr's log has an install from a proposal, whose facts carry provenance."""
    facts = await workspace.read(types=["reflexr:rule_installed"])
    return any(
        isinstance(fact.event, reflexr.core.RuleInstalled)
        and fact.event.provenance.get("proposal") == proposal_id
        for fact in facts
    )


async def _installed_from(workspace: Workspace, artifact_id: a.ArtifactId) -> WorkspaceRule | None:
    """The active stored rule installed from an artifact, if there is one.

    reflexr reads a stored rule's provenance one rule at a time; a workspace has at most 50.
    """
    for status in await workspace.rule_statuses():
        if status.origin == "stored":
            found = await workspace.get_rule(status.rule)
            if (found.provenance or {}).get("artifact") == artifact_id:
                return found
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
