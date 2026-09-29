"""``docplan-eval``: run the steps of docplan's evaluation loop against the server's database.

Serve docplan with ``DOCPLAN_DATABASE_URL`` set, so its workspaces outlive the server; chat,
and say what you think with ``/edits`` and ``/done``. Then, with the same database::

    docplan-eval judge      # people's feedback as a dataset, and the judge that agrees best
    docplan-eval replay     # the dataset's turns replayed against the agent, and judged
    docplan-eval measures   # task completion, drop-off and the rewrite rate

``replay`` calls the agent's model, as the server does; the other steps call none, unless
``DOCPLAN_JUDGE_MODEL`` asks for a DSPy judge.
"""

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, assert_never

from pydantic_ai import Agent
from pydantic_ai.models import Model
from rich.console import Console

from artifactr import Session, SystemActor, Workspace, Workspaces
from artifactr.sql import SqlStorage
from docplan.agent import build_agent
from docplan.app import TENANT, open_database
from docplan.artifacts import Doc, EditSize, Plan
from docplan.evals import calibrate, dataset, judge_from_environment, measures, replay

type Step = Literal["judge", "replay", "measures"]


async def run(
    step: Step,
    *,
    database_url: str,
    workspace_id: str,
    console: Console,
    window: timedelta = timedelta(hours=1),
    now: datetime | None = None,
    model: Model | str | None = None,
) -> None:
    """Run one step against a workspace in docplan's database, and print what it found.

    Args:
        step: ``judge``, ``replay`` or ``measures``.
        database_url: The server's database.
        workspace_id: The workspace to evaluate.
        console: Where to print.
        window: For the measures: how long a person has to come back, or to rewrite.
        now: For the measures: when the log is read; the current time by default.
        model: For replays: the agent's model; see :func:`docplan.agent.build_agent`.
    """
    engine = open_database(database_url)
    try:
        workspaces = Workspaces(SqlStorage(engine), types=[Doc, Plan])
        workspace = await workspaces.open(TENANT, workspace_id, actor=SystemActor())
        match step:
            case "judge":
                await show_judge(workspace, console)
            case "replay":
                await show_replay(workspace, console, build_agent(model))
            case "measures":
                now = now or datetime.now(UTC)
                await show_measures(workspace, console, window=window, now=now)
            case _:
                assert_never(step)
    finally:
        await engine.dispose()


async def show_judge(workspace: Workspace, console: Console) -> None:
    """Build the dataset, choose the judge that agrees best with people, and say how far."""
    examples = await dataset(workspace)
    judge, measured = await calibrate(judge_from_environment(), examples)
    agreement = measured.agreement
    too_big = agreement.fields["too_big"]
    console.print(f"{len(examples)} turns with people's edit_size feedback")
    console.print(
        f"{judge.name}@{judge.version} agrees with people {share(agreement.score)} "
        f"on {agreement.n} of them "
        f"(too_big: accuracy {share(too_big.accuracy)}, kappa {share(too_big.kappa)})"
    )


async def show_replay(
    workspace: Workspace, console: Console, agent: Agent[Session[None], Any]
) -> None:
    """Replay the dataset's turns against the agent, and compare the judge's verdicts."""
    examples = await dataset(workspace)
    judge = judge_from_environment()
    result = await replay(agent, examples, judge)
    verdicts = [verdict.value for verdict in result.verdicts(judge.name).values()]
    judged = [v for v in verdicts if isinstance(v, EditSize) and v.too_big]
    people = [e for e in examples if e.verdict and e.verdict.too_big]
    failed = [item for item in result.items if item.errors]
    console.print(
        f"Replayed {len(result.items)} turns: {judge.name} found {len(judged)} too big, "
        f"where people found {len(people)}; {len(failed)} failed"
    )


async def show_measures(
    workspace: Workspace, console: Console, *, window: timedelta, now: datetime
) -> None:
    """Measure task completion, drop-off and the rewrite rate."""
    found = await measures(workspace, window=window, now=now)
    console.print(
        f"task completion {share(found.completion)}, drop-off {share(found.drop_off)}, "
        f"rewrite rate {share(found.rewrites)}"
    )


def share(value: float | None) -> str:
    """A share or a score from 0 to 1, to two places; ``n/a`` when there is none."""
    return "n/a" if value is None else f"{value:.2f}"


def main(argv: list[str] | None = None) -> None:
    """Run one step of the evaluation loop."""
    parser = argparse.ArgumentParser(
        prog="docplan-eval", description="Evaluate docplan from the server's database."
    )
    parser.add_argument("step", choices=["judge", "replay", "measures"], help="what to run")
    parser.add_argument("--workspace", default="main", help="the workspace to evaluate")
    parser.add_argument(
        "--window",
        type=float,
        default=60,
        metavar="MINUTES",
        help="how long a person has to come back, or to rewrite, for the measures",
    )
    args = parser.parse_args(argv)
    database_url = os.environ.get("DOCPLAN_DATABASE_URL")
    if not database_url:
        sys.exit("docplan-eval: set DOCPLAN_DATABASE_URL to the server's database")
    asyncio.run(
        run(
            args.step,
            database_url=database_url,
            workspace_id=args.workspace,
            console=Console(),
            window=timedelta(minutes=args.window),
        )
    )
