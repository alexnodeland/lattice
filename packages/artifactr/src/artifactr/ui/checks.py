"""The checks that refuse what doesn't fit a form, before it commits (ADR-0075).

Give :func:`ui_checks` to artifactr's ``Workspaces(checks=...)``. artifactr records an answer
or a new artifact as given, and may not import a schema validator; its check hook runs these
before each command of their type commits, with the committing handle, so each reads the
workspace as the person who sent the command:

- **``answer_deferred``** to an ``ask_form`` request: the answer is the form's values, valid
  against the schema in the request's ``args``.
- **``create_artifact``** of a ``submission``: its form exists and the submitter may read it,
  it isn't closed or archived (:class:`FormClosed`), the version it was made against is the
  form's head (:class:`FormChanged`), its values are valid, and its id is its derivation. A
  submission to an app is checked the same way, but an app has no schema to check values
  against. An ``app`` is made by an agent alone.
- **``edit_artifact``:** a submission is never edited; a form's ``schema``, ``submissions`` and
  ``closed`` are changed only by its author or whom ``is_admin`` allows; and a person changes
  only an app's ``state``, so the HTML that runs is always an agent's.
- **``archive_artifact``:** a form, or a submission, is archived only by its author or whom
  ``is_admin`` allows.
- **``propose_change``:** the change it proposes is checked as the change itself, and a
  submission is never proposed: a person sends it.
- **``respond_to_proposal``:** an accepted change is checked again, as its proposer, against
  what is current, since artifactr applies it to the head; a reviewer's own ``changes`` aren't
  taken on a form, an app or a submission.

While forms are off in the workspace, an answer to ``ask_form`` is refused as ``not_enabled``.
Making or changing the forms' artifacts while their integration is off is artifactr's gate's to
refuse (:mod:`artifactr.ui.integrations`).

A check reads before the command commits and holds nothing: a form closed in between takes
one late submission. A check leaves to artifactr what artifactr refuses itself, such as a
second answer, a stale edit or an id in use.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from types import MappingProxyType
from typing import Any, Final, Literal, override

from pydantic import JsonValue, ValidationError

from artifactr.core import (
    Actor,
    AnswerDeferred,
    ArchiveArtifact,
    Artifact,
    Command,
    CreateArtifact,
    EditArtifact,
    Forbidden,
    InvalidState,
    NotEnabled,
    ProposeChange,
    ProposedChange,
    RespondToProposal,
    ValidationFailed,
    Versioned,
    acting_for,
    apply_patch,
    is_agent,
    same_participant,
    same_principal,
)
from artifactr.ui._common import refusal
from artifactr.ui.ids import submission_id
from artifactr.ui.integrations import FORMS
from artifactr.ui.types import (
    ASK_FORM,
    App,
    Form,
    FormRequest,
    Submission,
)
from artifactr.workspace import Check, Workspace
from lattice_core.integrations import Defaults, Integrations

__all__ = ["FormChanged", "FormClosed", "IsAdmin", "RefusalReason", "ui_checks"]

RefusalReason = Literal["changed", "closed"]
"""The ``reason`` in the payload of artifactr.ui's ``invalid_state`` refusals: :class:`FormChanged`
and :class:`FormClosed`. An ``invalid_state`` with none, to an answer, is artifactr's: the request
is answered already."""

IsAdmin = Callable[[Workspace], Awaitable[bool]]
"""Whether the workspace's actor may govern any form, and archive any submission, as their
authors may. The application answers it, from grantr's roles or its own: artifactr can't
import them (ADR-0075)."""

_GOVERNED: Final = ("schema", "submissions", "closed")
"""What of a form only its author, or an admin, changes."""

_KEPT: Final = frozenset({Form.kind, App.kind, Submission.kind})
"""The kinds whose proposals a reviewer accepts or rejects as proposed, without changes."""


class FormChanged(InvalidState):
    """A submission was made against a version of its form, or its app, that is not its head.

    Its payload's ``reason`` is ``"changed"``, with the target's ``artifact_id``, the ``version``
    the submission named and the ``head``, so a client shows "This form changed" without reading
    the message.
    """

    def __init__(self, target: Versioned[Any], version: int) -> None:
        super().__init__(
            f"{target.kind} {target.id} changed: the submission was made against version "
            f"{version}, and it is at {target.version}"
        )
        self.artifact_id = target.id
        self.version = version
        self.head = target.version

    @override
    def details(self) -> dict[str, JsonValue]:
        """Return the reason, the target and both versions."""
        return {
            "reason": "changed",
            "artifact_id": self.artifact_id,
            "version": self.version,
            "head": self.head,
        }


class FormClosed(InvalidState):
    """A submission was sent to a form that is closed, or to a form or an app that is archived.

    Its payload's ``reason`` is ``"closed"``, with the target's ``artifact_id``.
    """

    def __init__(self, target: Versioned[Any]) -> None:
        super().__init__(f"{target.kind} {target.id} is closed")
        self.artifact_id = target.id

    @override
    def details(self) -> dict[str, JsonValue]:
        """Return the reason and the target."""
        return {"reason": "closed", "artifact_id": self.artifact_id}


def ui_checks(
    *, is_admin: IsAdmin | None = None, integrations: Integrations | None = None
) -> Mapping[str, Check]:
    """Return artifactr.ui's checks, by command type, for ``Workspaces(checks=...)``.

    Merge them with the application's own, if it has any for the same command types, by
    calling both in one check of its own.

    Args:
        is_admin: Whether an actor may govern any form and archive any submission; only their
            authors may if omitted.
        integrations: Whether forms are on in a workspace, asked before an answer to
            ``ask_form``; each integration's default, lattice-core's ``Defaults``, if omitted.
    """
    rules = _Rules(is_admin, integrations or Defaults())
    return MappingProxyType(
        {
            "answer_deferred": _of(AnswerDeferred, rules.answer),
            "create_artifact": _of(CreateArtifact, rules.create),
            "edit_artifact": _of(EditArtifact, rules.edit),
            "archive_artifact": _of(ArchiveArtifact, rules.archive),
            "propose_change": _of(ProposeChange, rules.propose),
            "respond_to_proposal": _of(RespondToProposal, rules.respond),
        }
    )


def _of[C: Command](kind: type[C], check: Callable[[Workspace, C], Awaitable[None]]) -> Check:
    """A check of one command type, which artifactr calls only with a command of that type."""

    async def checked(workspace: Workspace, command: Command) -> None:
        if isinstance(command, kind):
            await check(workspace, command)

    return checked


class _Rules:
    """The checks, with who may govern a form, which ``is_admin`` widens, and what is on."""

    def __init__(self, is_admin: IsAdmin | None, integrations: Integrations) -> None:
        self._is_admin = is_admin
        self._integrations = integrations

    async def answer(self, workspace: Workspace, command: AnswerDeferred) -> None:
        run = await workspace.run(command.run_id)
        request = next((r for r in run.pending if r.tool_call_id == command.tool_call_id), None)
        if request is None or request.tool_name != ASK_FORM or command.tool_call_id in run.answers:
            return  # artifactr refuses an answer to no request, or a second one
        if not await self._integrations.is_enabled(
            workspace.tenant_id, workspace.workspace_id, FORMS
        ):
            raise NotEnabled(FORMS)
        try:
            form = FormRequest.model_validate(request.args)
        except ValidationError as error:
            raise refusal("the form asked is not one the subset holds", error) from error
        form.form_schema.validate_values(command.answer)

    async def create(self, workspace: Workspace, command: CreateArtifact) -> None:
        if command.kind == App.kind and not is_agent(workspace.actor):
            raise Forbidden("an app is an agent's: a person changes only its state")
        if command.kind == Submission.kind:
            await self._submitted(workspace, command)

    async def edit(self, workspace: Workspace, command: EditArtifact) -> None:
        await self._edit(workspace, command, on_head=False)

    async def archive(self, workspace: Workspace, command: ArchiveArtifact) -> None:
        artifact = await workspace.artifact(command.artifact_id)
        governed = isinstance(artifact.data, Form | Submission)
        if governed and not await self._governs(workspace, artifact):
            raise Forbidden(
                f"only {artifact.kind} {artifact.id}'s author, or an admin, archives it"
            )

    async def propose(self, workspace: Workspace, command: ProposeChange) -> None:
        await self._proposed(workspace, command.change, on_head=False)

    async def respond(self, workspace: Workspace, command: RespondToProposal) -> None:
        if command.decision == "reject":
            return
        proposal = await workspace.proposal(command.proposal_id)
        if proposal.status != "pending":
            return  # artifactr refuses a proposal resolved already
        change = proposal.change
        if isinstance(change, CreateArtifact):
            kind = change.kind
        else:
            kind = (await workspace.artifact(change.artifact_id)).kind
        if command.changes is not None and kind in _KEPT:
            raise Forbidden(f"a proposed {kind} change is accepted as proposed, without changes")
        await self._proposed(workspace.as_actor(proposal.proposed_by), change, on_head=True)

    async def _proposed(
        self, workspace: Workspace, change: ProposedChange, *, on_head: bool
    ) -> None:
        match change:
            case CreateArtifact(kind=Submission.kind):
                raise Forbidden("a submission is sent by its person, never proposed")
            case CreateArtifact():
                await self.create(workspace, change)
            case EditArtifact():
                await self._edit(workspace, change, on_head=on_head)
            case _:  # an archive
                await self.archive(workspace, change)

    async def _edit(self, workspace: Workspace, command: EditArtifact, *, on_head: bool) -> None:
        """Check an edit of the head, or, for an accepted proposal, its rebase onto the head."""
        artifact = await workspace.artifact(command.artifact_id)
        if isinstance(artifact.data, Submission):
            raise Forbidden(f"submission {artifact.id} is never edited: send another")
        stale = not on_head and artifact.version != command.base_version
        if stale or not isinstance(artifact.data, Form | App):
            return  # artifactr refuses a stale edit as a version conflict
        before = artifact.data.to_json()
        after = apply_patch(before, command.patch)
        if isinstance(artifact.data, App):
            outside = {*before, *after} - {"state"}
            if not is_agent(workspace.actor) and _changed(before, after, outside):
                raise Forbidden(f"a person changes only app {artifact.id}'s state")
        elif _changed(before, after, _GOVERNED) and not await self._governs(workspace, artifact):
            raise Forbidden(
                f"only form {artifact.id}'s author, or an admin, changes its schema, its "
                "submissions or whether it is closed"
            )

    async def _submitted(self, workspace: Workspace, command: CreateArtifact) -> None:
        try:
            submission = Submission.model_validate(command.data)
        except ValidationError as error:
            raise refusal("invalid submission data", error) from error
        if submission.form_id is not None:
            form = await workspace.get(Form, submission.form_id)
            _open(form, submission, closed=form.data.closed)
            form.data.form_schema.validate_values(submission.values)
            expected = _form_submission_id(form, submission, workspace.actor)
        else:
            app = await workspace.get(App, str(submission.app_id))  # it answers one of the two
            _open(app, submission, closed=False)
            expected = submission_id(app.id, nonce=_nonce(submission, "an app"))
        if command.artifact_id != expected:
            message = f"a submission's id is derived from what it answers: it is {expected} here"
            raise ValidationFailed(message, [_error(["artifact_id"], message)])

    async def _governs(self, workspace: Workspace, artifact: Versioned[Artifact]) -> bool:
        first = (await workspace.revisions(artifact.id))[0]
        if _authored(first.actor, workspace.actor):
            return True
        return self._is_admin is not None and await self._is_admin(workspace)


def _open(target: Versioned[Any], submission: Submission, *, closed: bool) -> None:
    if closed or target.archived:
        raise FormClosed(target)
    if submission.version != target.version:
        raise FormChanged(target, submission.version)


def _form_submission_id(form: Versioned[Form], submission: Submission, actor: Actor) -> str:
    policy = form.data.submissions
    if policy == "many":
        return submission_id(form.id, nonce=_nonce(submission, "a form that takes many"))
    if submission.nonce is not None:
        message = f"a submission to a form that takes {policy.replace('_', ' ')} has no nonce"
        raise ValidationFailed(message, [_error(["data", "nonce"], message)])
    if policy == "once":
        return submission_id(form.id)
    principal = acting_for(actor)
    if principal is None:
        raise Forbidden(f"form {form.id} takes one submission a person: send it as one")
    return submission_id(form.id, principal=principal.participant)


def _nonce(submission: Submission, to: str) -> str:
    if submission.nonce is None:
        message = f"a submission to {to} carries the nonce its id is derived from"
        raise ValidationFailed(message, [_error(["data", "nonce"], message)])
    return submission.nonce


def _authored(author: Actor, actor: Actor) -> bool:
    """Whether an actor is an artifact's author, or acts for whom its author acted for.

    An agent's run acts for whoever started it, so the person whose run made a form may close it.
    """
    return same_participant(author, actor) or (
        acting_for(author) is not None and same_principal(author, actor)
    )


def _changed(
    before: dict[str, JsonValue], after: dict[str, JsonValue], keys: Iterable[str]
) -> bool:
    return any(before.get(key) != after.get(key) for key in keys)


def _error(loc: list[JsonValue], message: str) -> JsonValue:
    return {"type": "value_error", "loc": loc, "msg": message}
