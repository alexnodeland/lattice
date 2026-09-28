"""The agent: artifactr's capability, plus tools for working with plans."""

import os
from typing import Any

from pydantic_ai import Agent, DeferredToolRequests, FunctionToolset, ModelRetry, RunContext
from pydantic_ai.models import Model

from artifactr import ArtifactWorkspace, Session
from artifactr.agent import describe_outcome
from docplan.artifacts import Doc, Plan, Status

DEFAULT_MODEL = "anthropic:claude-sonnet-5-5"

INSTRUCTIONS = """\
You help a small team write a document, then turn it into a plan of work.

- Draft and revise the document (a `doc`) with the team. Keep edits small.
- When the document is settled, create a `plan` that implements it and add its tasks.
- Plans are reviewed: your plan changes become proposals the team accepts or rejects.
- Ask the team when something important is unclear; do not guess.
"""

plan_tools = FunctionToolset[Session[None]]()


@plan_tools.tool
async def add_task(
    ctx: RunContext[Session[None]], plan_id: str, title: str, owner: str | None = None
) -> str:
    """Add a task to a plan.

    Args:
        plan_id: The plan to add to.
        title: What needs doing.
        owner: Who should do it, if known.
    """
    plan = await ctx.deps.workspace.get(Plan, plan_id)
    edit = plan.edit(lambda p: p.add_task(title, owner), thread_id=ctx.deps.thread_id)
    return describe_outcome(await ctx.deps.workspace.commit(edit))


@plan_tools.tool
async def set_task_status(
    ctx: RunContext[Session[None]], plan_id: str, task_id: str, status: Status
) -> str:
    """Move a task of a plan to todo, doing or done.

    Args:
        plan_id: The plan the task belongs to.
        task_id: The task, as shown in the plan.
        status: The new status.
    """
    plan = await ctx.deps.workspace.get(Plan, plan_id)
    if task_id not in plan.data.tasks:
        raise ModelRetry(f"{plan_id} has no task {task_id}; the plan lists its task ids.")
    edit = plan.edit(lambda p: p.set_status(task_id, status), thread_id=ctx.deps.thread_id)
    return describe_outcome(await ctx.deps.workspace.commit(edit))


def build_agent(model: Model | str | None = None) -> Agent[Session[None], Any]:
    """Build the docplan agent.

    Args:
        model: A pydantic-ai model or model name. Defaults to the ``DOCPLAN_MODEL`` environment
            variable, then to a current Claude model.
    """
    return Agent(
        model or os.environ.get("DOCPLAN_MODEL", DEFAULT_MODEL),
        deps_type=Session[None],
        instructions=INSTRUCTIONS,
        output_type=[str, DeferredToolRequests],
        toolsets=[plan_tools],
        capabilities=[ArtifactWorkspace(types=[Doc, Plan], ask=True)],
        defer_model_check=True,
    )
