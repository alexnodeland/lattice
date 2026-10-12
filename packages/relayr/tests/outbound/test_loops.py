"""Phase 2's exit criteria, over both libraries' in-memory storage and every ledger.

Under forced retries, a rule's proposal and notice each appear once. Two rules that answer each
other stop at the depth limit.
"""

import asyncio
import functools
from datetime import timedelta

from pydantic import BaseModel

import artifactr.core as a
import reflexr
import reflexr.workspace as r
from reflexr.core import RuleErrored
from relayr.events import MessagePosted
from relayr.ledger import Ledger
from relayr.outbound import Outbound, rule_actor
from tests.app_types import Note
from tests.stack import KEY, Process, Stack, notices, until

FLAKY = reflexr.Rule(
    name="app:review",
    when=reflexr.on(MessagePosted).where(reflexr.F.author.kind.eq("user")),
    then=reflexr.run("review"),
    retry=reflexr.RetryPolicy(max_attempts=3, backoff=timedelta(milliseconds=1)),
)


async def caught_up(ledger: Ledger, head: int) -> bool:
    return await ledger.cursor(KEY) >= head


async def quiet(process: Process, ledger: Ledger) -> None:
    """Run rules and follow the log until neither has anything left to do."""
    while True:
        settled = await process.reactor.settle()
        log = await process.collaboration.open(*KEY, actor=a.SystemActor())
        head = await log.head_seq()
        await until(functools.partial(caught_up, ledger, head))
        await asyncio.sleep(0.01)  # retries wait their backoff
        again = await process.reactor.settle()
        if not (settled.attempts or again.attempts or await log.head_seq() > head):
            return


async def test_a_retried_runs_proposal_and_notice_each_appear_once(
    ledger: Ledger, stack: Stack
) -> None:
    attempts: list[int] = []

    async def review(reaction: r.Reaction[Outbound]) -> None:
        acting = reaction.deps.acting(reaction)
        await acting.create(Note(text="draft"), rationale="asked for")
        await acting.notice("Proposed a note.")
        attempts.append(reaction.attempt)
        if reaction.attempt < 3:
            raise RuntimeError("the attempt fails after acting")

    app = stack.process(ledger, rules=[FLAKY], actions={"review": review})
    await app.post("please draft a note")
    await quiet(app, ledger)
    assert attempts == [1, 2, 3]
    workspace = await app.collaboration.open(*KEY, actor=a.SystemActor())
    [proposal] = await workspace.proposals()
    assert proposal.proposed_by == rule_actor("app:review")
    assert notices(await workspace.read()) == [(rule_actor("app:review"), "Proposed a note.")]


class Says(BaseModel):
    says: str


def answering(name: str, heard: str, says: str) -> reflexr.Rule:
    return reflexr.Rule(
        name=f"app:{name}",
        when=reflexr.on(MessagePosted).where(reflexr.F.content.eq(heard)),
        then=reflexr.run("answer", says=says),
    )


async def test_two_rules_that_answer_each_other_stop_at_the_depth_limit(
    ledger: Ledger, stack: Stack
) -> None:
    async def answer(reaction: r.Reaction[Outbound], params: Says) -> None:
        await reaction.deps.acting(reaction).notice(params.says)

    app = stack.process(
        ledger,
        rules=[answering("ping", "ping", "pong"), answering("pong", "pong", "ping")],
        actions={"answer": r.with_params(answer, Says)},
        max_depth=4,
    )
    await app.post("ping")
    await quiet(app, ledger)
    assert [(e.depth, e.event.model_dump()["content"]) for e in await stack.bridged()] == [
        (0, "ping"),
        (1, "pong"),
        (2, "ping"),
        (3, "pong"),
        (4, "ping"),
    ]
    reader = r.Workspaces(stack.reflexr_storage)
    log = await (await reader.open(*KEY, actor=reflexr.SystemActor())).read()
    last = log[-1].event
    assert isinstance(last, RuleErrored)
    assert "beyond the limit of 4" in last.error
