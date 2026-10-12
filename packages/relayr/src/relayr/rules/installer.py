"""relayr's own rules, which put the drafts people accept live in reflexr, and archive them.

`relayr:install-rule` fires on an accepted proposal, and `relayr:archive-rule` on an archived
`rule` artifact. Neither trusts the bridged event: each re-reads artifactr, as its rule's own
participant, and acts only on what artifactr's own record says.

- **The proposal was accepted**, and its artifact is a `rule`.
- **The artifact is still at the version the acceptance made**, or, for an archive, at the version
  that archived it. A later change acts for itself.
- **The person who accepted, or archived, may make the change**: install, update or archive the
  rule. They are the actor of the artifact's revision at that version, which artifactr records
  with the proposal it applied, and `may_change` says whether they may.

A forged event therefore installs nothing.
"""

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final, Literal

from pydantic import JsonValue

import artifactr
import artifactr.core as a
import reflexr.core
from reflexr import F, Rule, on, run
from reflexr.workspace import Action, Reaction, Workspace, WorkspaceRule
from relayr.events import ArtifactArchived, ProposalResolved
from relayr.outbound import Outbound, RunActions, rule_actor
from relayr.rules.drafts import RuleDraft

type Change = Literal["install_rule", "update_rule", "archive_rule"]
"""A change to a stored rule, named as reflexr's action for it is, without its prefix."""

type MayChange = Callable[[str, str, a.UserActor, Change], Awaitable[bool]]
"""Whether a person may make a change to stored rules in a tenant's workspace:
``(tenant, workspace, person, change)``."""


INSTALL_RULE: Final = Rule(
    name="relayr:install-rule",
    description="A proposal was accepted. If it drafts a rule, install it.",
    when=on(ProposalResolved).where(F.decision.eq("accept")),
    then=run("install-rule"),
)

ARCHIVE_RULE: Final = Rule(
    name="relayr:archive-rule",
    description="A rule artifact was archived. Archive the rule it installed.",
    when=on(ArtifactArchived).where(F.kind.eq(RuleDraft.kind)),
    then=run("archive-rule"),
)

RULES: Final = [INSTALL_RULE, ARCHIVE_RULE]
"""relayr's rules from chat, for the application's reflexr workspaces."""


class Installer:
    """The actions of relayr's rules from chat. Register `actions` with the reactor.

    Args:
        outbound: The adapter the runs post their notices through.
        artifactr: The workspaces the runs re-read.
        may_change: Whether the person who accepted a draft, or archived it, may make the change
            to its rule. Without it, any person may, as without access control.
    """

    def __init__(
        self,
        outbound: Outbound,
        artifactr: artifactr.Workspaces,
        *,
        may_change: MayChange | None = None,
    ) -> None:
        self._outbound = outbound
        self._artifactr = artifactr
        self._may_change = may_change

    @property
    def actions(self) -> Mapping[str, Action[Any]]:
        """The rules' actions, by the names `RULES` run."""
        return {"install-rule": self.install, "archive-rule": self.archive}

    async def install(self, reaction: Reaction[Any]) -> None:
        """Install, or update, the rule an accepted proposal drafted."""
        [envelope] = reaction.events
        assert isinstance(envelope.event, ProposalResolved)
        resolved = envelope.event
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
        acting = self._outbound.acting(reaction)
        rule = RuleDraft.model_validate(revision.data).rule
        target = reaction.workspace
        installed = await _installed_from(target, revision.artifact_id)
        change: Change = "install_rule" if installed is None else "update_rule"
        approver = await self._approver(reaction, acting, revision, change, proposal.thread_id)
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
            elif installed.rule.name != rule.name:
                await _tell(
                    acting,
                    f"{installed.rule.name} can't be renamed {rule.name}: archive it, and draft "
                    "the new rule apart.",
                    proposal.thread_id,
                )
                return
            else:
                changed = await target.update_rule(
                    rule, expected_version=installed.version, provenance=provenance
                )
        except reflexr.core.Rejection as rejection:
            await _tell(
                acting, f"{rule.name} wasn't installed: {_why(rejection)}", proposal.thread_id
            )
            return
        live = f"{rule.name} is live, at version {changed.stored.version}."
        await _tell(acting, live, proposal.thread_id)

    async def archive(self, reaction: Reaction[Any]) -> None:
        """Archive the rule an archived `rule` artifact installed."""
        [envelope] = reaction.events
        assert isinstance(envelope.event, ArtifactArchived)
        archived = envelope.event
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
        change: Change = "archive_rule"
        if await self._approver(reaction, acting, revision, change, archived.thread_id) is None:
            return
        name = installed.rule.name
        reason = f"its artifact {archived.artifact_id} was archived"
        await target.archive_rule(name, expected_version=installed.version, reason=reason)
        await _tell(acting, f"{name} is archived.", archived.thread_id)

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
        change: Change,
        thread_id: a.ThreadId | None,
    ) -> a.UserActor | None:
        """The person who made a revision, if they may make the change."""
        person = revision.actor
        workspace = reaction.workspace
        if isinstance(person, a.UserActor) and (
            self._may_change is None
            or await self._may_change(workspace.tenant_id, workspace.workspace_id, person, change)
        ):
            return person
        verb = change.removesuffix("_rule")
        await _tell(acting, f"Only a person who may {verb} rules can {verb} this one.", thread_id)
        return None


async def _installed_from(workspace: Workspace, artifact_id: a.ArtifactId) -> WorkspaceRule | None:
    """The active stored rule installed from an artifact, if there is one."""
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
