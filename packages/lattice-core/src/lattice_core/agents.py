"""The agents bridge: capabilities offered to a pydantic-ai agent, each called through the enforcer.

Behind the ``agents`` extra. :func:`toolset` is a pydantic-ai toolset whose tools are the
capabilities the registry offers in a run's scope, rebuilt at each run step, and whose every call
goes through :class:`~lattice_core.enforcement.Enforcer` (lattice RFC-0011)::

    agent = Agent(model, deps_type=Session, toolsets=[toolset(enforcer, context_of, keep_taint)])

- **A tool's name** is the capability's, each ``.`` written ``__``, since model APIs allow only
  letters, digits, ``_`` and ``-``: ``artifactr.edit_text`` is ``artifactr__edit_text``.
- **An approval** pauses the run: a call the enforcer defers raises pydantic-ai's
  ``ApprovalRequired`` with the approval's id in its metadata, under :data:`APPROVAL`. The runner
  resumes it once the approval is answered, with the call approved and that metadata, and the tool
  calls the enforcer again with the id, which it checks.
- **A refusal,** and a provider's error, reach the model as pydantic-ai's ``ToolFailed``, with
  the reason; the run goes on.
- **Taint** is the application's to keep between calls: ``context`` builds each call's context,
  its taint included, and ``marked`` is given the taint each call leaves, even one that failed.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Final

from pydantic import JsonValue
from pydantic_ai import ApprovalRequired, RunContext, Tool, ToolFailed
from pydantic_ai.toolsets import DynamicToolset, FunctionToolset

from lattice_core.capabilities import CallContext, Capability
from lattice_core.enforcement import ApprovalPending, CallFailed, Enforcer, Refused
from lattice_core.taint import Taint

__all__ = ["APPROVAL", "ContextOf", "Marked", "tool_name", "toolset"]

APPROVAL: Final = "approval"
"""The key of the approval's id in a deferred call's metadata, given back when it resumes."""

type ContextOf[D] = Callable[[RunContext[D]], Awaitable[CallContext]]
"""Builds a call's context from the run's: its scope, its caller, its taint, where it came from."""

type Marked[D] = Callable[[RunContext[D], Taint], Awaitable[None]]
"""Keeps the taint a call left, for the run's next calls and the runs it starts."""


def tool_name(capability: str) -> str:
    """Return the tool's name for a capability's: each ``.`` written ``__``."""
    return capability.replace(".", "__")


def toolset[D](enforcer: Enforcer, context: ContextOf[D], marked: Marked[D]) -> DynamicToolset[D]:
    """Return a toolset of the capabilities offered in each run's scope, each through the enforcer.

    Args:
        enforcer: The enforcement path, whose registry offers the capabilities.
        context: Builds each call's context from the run's.
        marked: Keeps the taint each call leaves.

    Raises:
        ValueError: At a run step, if two capabilities offered in its scope have one tool name.
    """

    async def build(ctx: RunContext[D]) -> FunctionToolset[D]:
        scope = (await context(ctx)).scope
        tools: dict[str, Tool[D]] = {}
        for capability in enforcer.registry.capabilities(scope):
            name = tool_name(capability.name)
            if name in tools:
                raise ValueError(f"two capabilities are the tool {name} here")
            tools[name] = _tool(enforcer, capability, context, marked)
        return FunctionToolset(list(tools.values()))

    return DynamicToolset(build)


def _tool[D](
    enforcer: Enforcer, capability: Capability, context: ContextOf[D], marked: Marked[D]
) -> Tool[D]:
    async def call(ctx: RunContext[D], **arguments: Any) -> JsonValue:
        metadata: dict[str, object] = dict(ctx.tool_call_metadata or {})
        given = metadata.get(APPROVAL) if ctx.tool_call_approved else None
        approval = given if isinstance(given, str) else None
        try:
            called = await enforcer.call(
                capability.name, arguments, await context(ctx), approval=approval
            )
        except ApprovalPending as pending:
            raise ApprovalRequired(metadata={APPROVAL: pending.approval}) from None
        except Refused as refused:
            raise ToolFailed(f"refused: {refused}") from None
        except CallFailed as failed:
            await marked(ctx, failed.taint)
            raise ToolFailed(str(failed)) from failed.error
        await marked(ctx, called.taint)
        return called.result.output

    return Tool.from_schema(
        call,
        name=tool_name(capability.name),
        description=capability.description,
        json_schema=capability.input_schema,
        takes_ctx=True,
    )
