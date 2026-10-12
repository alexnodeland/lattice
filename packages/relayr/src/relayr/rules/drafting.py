"""The chat agent drafts rules: a tool that checks a draft, previews it, and proposes it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, override

from pydantic_ai import FunctionToolset, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability

import artifactr
import artifactr.core as a
import reflexr
import reflexr.workspace
from artifactr.agent import Session, describe_outcome, submit
from reflexr import Event, Rule
from reflexr.core import StoredRules
from relayr.rules.drafts import RuleDraft, check_draft
from relayr.rules.preview import preview

PREVIEWER = reflexr.SystemActor(name="relayr")
"""Who reads reflexr's log for a preview."""

INSTRUCTIONS = (
    "When a person asks for something to happen whenever something else does, draft a rule "
    "with `draft_rule`. It checks the rule and proposes it; it goes live once a person accepts "
    "it. To change a rule, draft it again with its artifact's id."
)


@dataclass
class RuleDrafting(AbstractCapability[Session[Any]]):
    """Give the chat agent `draft_rule`, which checks a rule, previews it, and proposes it.

    Args:
        automation: reflexr's workspaces, whose log the preview replays.
        events: The event types those workspaces accept, by name.
        stored_rules: Their configuration of stored rules.
        window: How far back the preview looks.
    """

    automation: reflexr.workspace.Workspaces
    events: Mapping[str, type[Event]]
    stored_rules: StoredRules
    window: timedelta = timedelta(days=7)
    _toolset: FunctionToolset[Session[Any]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._toolset = self._tools()

    @override
    def get_toolset(self) -> FunctionToolset[Session[Any]]:
        """Return `draft_rule`."""
        return self._toolset

    @override
    def get_instructions(self) -> str:
        """Return when to draft a rule."""
        return INSTRUCTIONS

    def _tools(self) -> FunctionToolset[Session[Any]]:
        toolset = FunctionToolset[Session[Any]]()

        # The tool annotates its context as RunContext[...] literally: pydantic-ai detects
        # context-taking tools by that annotation.
        @toolset.tool
        async def draft_rule(
            ctx: RunContext[Session[Any]],
            rule: Rule,
            rationale: str,
            artifact_id: str | None = None,
        ) -> str:
            """Propose a rule, or a change to one, for a person to accept.

            Args:
                rule: The rule, in one of the namespaces stored rules may use.
                rationale: Why, in the person's words.
                artifact_id: The `rule` artifact to change, if this changes a drafted rule.
            """
            problems = check_draft(rule, events=self.events, stored_rules=self.stored_rules)
            if problems:
                raise ModelRetry("The rule can't be installed: " + "; ".join(problems))
            workspace = ctx.deps.workspace
            change = await _change(workspace, rule, artifact_id, ctx.deps.thread_id)
            fired = await self._preview(workspace, rule)
            outcome = await submit(
                workspace, change, propose=True, rationale=f"{rationale}\n\n{fired}"
            )
            return describe_outcome(outcome)

        return toolset

    async def _preview(self, workspace: artifactr.Workspace, rule: Rule) -> str:
        """What the preview found, for the proposal's rationale."""
        replayed = await self.automation.open(
            workspace.tenant_id, workspace.workspace_id, actor=PREVIEWER
        )
        since = self.automation.clock() - self.window
        previewed = await preview(replayed, rule, since=since)
        seen = "" if previewed.complete else ", among the newest events"
        return f"It would have fired {previewed.firings} times since {since:%Y-%m-%d}{seen}."


async def _change(
    workspace: artifactr.Workspace,
    rule: Rule,
    artifact_id: str | None,
    thread_id: a.ThreadId,
) -> a.CreateArtifact | a.EditArtifact:
    """A new `rule` artifact, or an edit of the one named."""
    if artifact_id is None:
        return a.create_artifact(RuleDraft(rule=rule), thread_id=thread_id)
    try:
        current = await workspace.get(RuleDraft, artifact_id)
    except a.NotFound as missing:
        raise ModelRetry(str(missing)) from missing
    return current.edit(_with(rule), thread_id=thread_id)


def _with(rule: Rule) -> Callable[[RuleDraft], None]:
    def change(draft: RuleDraft) -> None:
        draft.rule = rule

    return change
