"""The attribute names artifactr puts on spans and metrics, in one place.

The OpenTelemetry GenAI conventions are still in development; if their names change, they
change here. :func:`attribution` builds the attributes every span artifactr owns or wraps
carries: the thread as the session, the person as the user, and artifactr's own ids.
"""

from typing import Final

from opentelemetry.util.types import AttributeValue

from artifactr.core import Actor, RunId, TenantId, ThreadId, UserActor, WorkspaceId

# ─── conventions shared with other instrumentation ────────────────────────────

SESSION_ID: Final = "session.id"
"""The session: artifactr's thread id. Langfuse groups traces into sessions by it."""

USER_ID: Final = "user.id"
"""The person a span acts for: a user actor's id."""

ERROR_TYPE: Final = "error.type"
"""The class of an unexpected error."""

GEN_AI_CONVERSATION_ID: Final = "gen_ai.conversation.id"
"""The GenAI conversation: artifactr's thread id, as pydantic-ai sets it on its own spans."""

GEN_AI_OPERATION_NAME: Final = "gen_ai.operation.name"
"""The GenAI operation, such as ``invoke_workflow``."""

GEN_AI_WORKFLOW_NAME: Final = "gen_ai.workflow.name"
"""The name of a GenAI workflow: ``turn`` for artifactr's turns."""

GEN_AI_TOOL_NAME: Final = "gen_ai.tool.name"
"""A tool's name."""

GEN_AI_TOKEN_TYPE: Final = "gen_ai.token.type"
"""``input`` or ``output``, for token counts."""

LANGFUSE_OBSERVATION_TYPE: Final = "langfuse.observation.type"
"""How Langfuse shows a span, such as ``chain``."""

# ─── artifactr's ids ──────────────────────────────────────────────────────────

TENANT_ID: Final = "artifactr.tenant.id"
WORKSPACE_ID: Final = "artifactr.workspace.id"
THREAD_ID: Final = "artifactr.thread.id"
RUN_ID: Final = "artifactr.run.id"
"""artifactr's run id, which spans a run's pauses. pydantic-ai's own run id is per attempt."""
ARTIFACT_ID: Final = "artifactr.artifact.id"
PROPOSAL_ID: Final = "artifactr.proposal.id"

# ─── what happened ────────────────────────────────────────────────────────────

ACTOR_KIND: Final = "artifactr.actor.kind"
"""The kind of actor: ``user``, ``agent``, ``external_agent`` or ``system``."""

COMMAND_TYPE: Final = "artifactr.command.type"
"""A command's ``type``, such as ``edit_artifact``."""

OUTCOME: Final = "artifactr.outcome"
"""What a command did: ``applied``, ``proposed``, ``resolved``, ``recorded`` or ``rejected``."""

REJECTION: Final = "artifactr.rejection"
"""Why a command was rejected: the rejection's ``code``, such as ``version_conflict``."""

ARTIFACT_KIND: Final = "artifactr.artifact.kind"
"""An artifact's registered type name."""

ARTIFACT_VERSION: Final = "artifactr.artifact.version"
"""The version an artifact is at after a change."""

PATCH_KIND: Final = "artifactr.patch.kind"
"""``json_patch`` or ``text_edits``."""

PATCH_SIZE: Final = "artifactr.patch.size"
"""How many operations or text edits a patch has."""

CHANGE: Final = "artifactr.change"
"""What happened to an artifact: ``created``, ``changed`` or ``archived``."""

PROPOSAL_ACTION: Final = "artifactr.proposal.action"
"""What happened to a proposal: ``created``, ``accepted`` or ``rejected``."""

MESSAGE_KIND: Final = "artifactr.message.kind"
"""What a posted message is: a ``message``, or a ``notice``."""

TURN_TRIGGER: Final = "artifactr.turn.trigger"
"""What started a turn: ``message`` or ``resume``."""

TURN_OUTCOME: Final = "artifactr.turn.outcome"
"""How a turn ended: ``completed``, ``paused``, ``stopped`` or ``failed``."""

RUN_STATUS: Final = "artifactr.run.status"
"""How a run segment ended: ``completed``, ``paused``, ``stopped`` or ``failed``."""

RUN_REASON: Final = "artifactr.run.reason"
"""Why a run segment failed, when it has a typed reason, such as ``guardrail_blocked``."""

TOOL_STATUS: Final = "artifactr.tool.status"
"""How a tool call ended: ``ok``, ``retry`` or ``error``."""

FEEDBACK_TYPE: Final = "artifactr.feedback.type"
"""A feedback type's registered name."""

FEEDBACK_TARGET: Final = "artifactr.feedback.target"
"""What feedback is about: ``artifact``, ``thread``, ``turn`` or ``message``."""

CLOSE_CODE: Final = "artifactr.stream.close_code"
"""The WebSocket close code a thread-protocol connection ended with."""


def attribution(
    *,
    tenant_id: TenantId,
    workspace_id: WorkspaceId,
    thread_id: ThreadId | None = None,
    run_id: RunId | None = None,
    actor: Actor | None = None,
    user: Actor | None = None,
) -> dict[str, AttributeValue]:
    """Return the attributes that attribute a span to its tenant, workspace, thread and actor.

    Args:
        tenant_id: The tenant.
        workspace_id: The workspace.
        thread_id: The thread, which is also the session.
        run_id: artifactr's run.
        actor: Who acts; its kind is recorded, and its id as the user when it is a person.
        user: The person the span acts for, when that is not ``actor`` (a person's message
            starts an agent's run). Defaults to ``actor``.
    """
    attributes: dict[str, AttributeValue] = {TENANT_ID: tenant_id, WORKSPACE_ID: workspace_id}
    if thread_id is not None:
        attributes |= {
            SESSION_ID: thread_id,
            GEN_AI_CONVERSATION_ID: thread_id,
            THREAD_ID: thread_id,
        }
    if run_id is not None:
        attributes[RUN_ID] = run_id
    if actor is not None:
        attributes[ACTOR_KIND] = actor.kind
    person = user or actor
    if isinstance(person, UserActor):
        attributes[USER_ID] = person.id
    return attributes
