"""The agents bridge: a run's capabilities as tools, each called through the enforcer, an approval
pausing the run and resuming it, refusals told to the model, and taint kept (RFC-0011)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    DeferredToolResults,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RunContext,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from lattice_core.agents import APPROVAL, tool_name, toolset
from lattice_core.approvals import Answer, Answerers, FakeApprovals, NoCoverage, Subject
from lattice_core.approvals import arguments_digest as digest
from lattice_core.capabilities import (
    CallContext,
    Capability,
    FakeProvider,
    Gate,
    Registry,
    RunCaller,
    Scope,
    ToolResult,
)
from lattice_core.enforcement import Enforcer, FakeAudit, FakeCounter, FixedCeilings, FixedTaint
from lattice_core.integrations import Defaults
from lattice_core.settings import SettingsDefaults
from lattice_core.taint import Cause, Clean, Taint, Tainted

HERE = Scope(tenant_id="acme", workspace_id="docs")
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def capability(name: str, **changes: Any) -> Capability:
    fields: dict[str, Any] = {
        "name": name,
        "version": "1.0.0",
        "description": f"The {name} tool.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        "output_schema": None,
        "provider": "builtin",
        "tier": "read",
        "effects": frozenset[str](),
        "reversibility": "none",
        "gate": Gate(integration=None, action="test:call"),
    }
    return Capability.model_validate(fields | changes)


class Policy:
    def __init__(self, answerers: Answerers | None) -> None:
        self.answerers = answerers

    async def needed(self, _capability: Capability, _context: CallContext, /) -> Answerers | None:
        return self.answerers


class Run:
    """A run's world: an enforcer of fakes, the run's taint, and a scripted model."""

    def __init__(
        self,
        *capabilities: Capability,
        results: dict[str, ToolResult | Exception] | None = None,
        allowed: bool = True,
        answerers: Answerers | None = None,
    ) -> None:
        self.store = FakeApprovals()
        self.taint: Taint = Clean()
        self.seen: list[list[ModelMessage]] = []
        self.offered: list[list[str]] = []

        async def authorize(_context: CallContext, _action: str) -> bool:
            return allowed

        self.enforcer = Enforcer(
            Registry(FakeProvider("builtin", *capabilities, results=results)),
            integrations=Defaults({}),
            authorize=authorize,
            ceilings=FixedCeilings(),
            settings=SettingsDefaults({}),
            counter=FakeCounter(),
            taint=FixedTaint(),
            approvals=Policy(answerers),
            coverage=NoCoverage(),
            store=self.store,
            audit=FakeAudit(),
            clock=lambda: NOW,
        )

    async def context(self, _ctx: RunContext[None]) -> CallContext:
        return CallContext(
            scope=HERE,
            caller=RunCaller(id="run_1", agent="helper", on_behalf_of="alex"),
            taint=self.taint,
            correlation_id="run_1",
            surface="portalr",
        )

    async def marked(self, _ctx: RunContext[None], taint: Taint) -> None:
        self.taint = taint

    def agent(self, *steps: ModelResponse) -> Agent[None, str | DeferredToolRequests]:
        script = list(steps)

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            self.seen.append(list(messages))
            self.offered.append(sorted(tool.name for tool in info.function_tools))
            return script.pop(0)

        return Agent(
            FunctionModel(respond),
            deps_type=type(None),
            output_type=[str, DeferredToolRequests],
            toolsets=[toolset(self.enforcer, self.context, self.marked)],
        )

    def returned(self, request: int) -> list[ToolReturnPart]:
        last = self.seen[request][-1]
        assert isinstance(last, ModelRequest)
        return [part for part in last.parts if isinstance(part, ToolReturnPart)]


def call(tool: str, call_id: str = "c1", **args: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args, tool_call_id=call_id)])


def say(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def test_a_tools_name_is_the_capabilitys_with_each_dot_written_twice_underscored() -> None:
    assert tool_name("mcp.github.create_issue") == "mcp__github__create_issue"


async def test_the_runs_capabilities_are_its_tools_and_a_call_goes_through_the_enforcer() -> None:
    run = Run(capability("notes.read"), results={"notes.read": ToolResult(output={"text": "hi"})})
    agent = run.agent(call("notes__read", text="plan"), say("Read."))
    result = await agent.run("Read my notes")
    assert result.output == "Read."
    assert run.offered[0] == ["notes__read"]
    [returned] = run.returned(1)
    assert returned.content == {"text": "hi"}
    [tool] = (await _definitions(run)).values()
    assert (tool.description, tool.parameters_json_schema) == (
        "The notes.read tool.",
        capability("notes.read").input_schema,
    )


async def _definitions(run: Run) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.update({tool.name: tool for tool in info.function_tools})
        return say("Listed.")

    agent = Agent(
        FunctionModel(respond),
        deps_type=type(None),
        toolsets=[toolset(run.enforcer, run.context, run.marked)],
    )
    await agent.run("List")
    return seen


async def test_the_taint_a_call_leaves_is_kept_for_the_next() -> None:
    fetch = capability("web.fetch", effects=frozenset({"reads_untrusted"}))
    run = Run(fetch, results={"web.fetch": ToolResult(output="a page")})
    await run.agent(call("web__fetch", text="x"), say("Fetched.")).run("Fetch it")
    assert run.taint == Tainted(causes=(Cause(capability="web.fetch", at=NOW),))


async def test_a_refusal_reaches_the_model_and_the_run_goes_on() -> None:
    run = Run(capability("notes.read"), allowed=False)
    result = await run.agent(call("notes__read", text="x"), say("I can't.")).run("Read")
    assert result.output == "I can't."
    told = str(run.seen[1][-1])
    assert "refused: the caller doesn't hold test:call" in told


async def test_a_providers_error_reaches_the_model_with_the_taint_kept() -> None:
    fetch = capability("web.fetch", effects=frozenset({"reads_untrusted"}))
    run = Run(fetch, results={"web.fetch": TimeoutError("slow")})
    result = await run.agent(call("web__fetch", text="x"), say("It failed.")).run("Fetch")
    assert result.output == "It failed."
    assert "TimeoutError: slow" in str(run.seen[1][-1])
    assert isinstance(run.taint, Tainted)


async def test_an_approval_pauses_the_run_and_resumes_it_once_answered() -> None:
    sam = Answerers(subjects=frozenset({"sam"}))
    run = Run(
        capability("mail.send"), results={"mail.send": ToolResult(output="sent")}, answerers=sam
    )
    agent = run.agent(call("mail__send", "c1", text="hi"), say("Sent."))
    paused = await agent.run("Mail them")
    assert isinstance(paused.output, DeferredToolRequests)
    [request] = paused.output.approvals
    approval = paused.output.metadata[request.tool_call_id][APPROVAL]
    assert approval == "apr_1"
    answer = Answer(approved=True, arguments_digest=digest({"text": "hi"}), surface="portalr")
    await run.store.answer(approval, answer, subject=Subject(id="sam"))
    resumed = await agent.run(
        message_history=paused.all_messages(),
        deferred_tool_results=DeferredToolResults(
            approvals={request.tool_call_id: True},
            metadata={request.tool_call_id: {APPROVAL: approval}},
        ),
    )
    assert resumed.output == "Sent."
    [returned] = run.returned(1)
    assert returned.content == "sent"


async def test_a_resumed_call_without_an_approvals_id_is_asked_again() -> None:
    run = Run(capability("mail.send"), answerers=Answerers(subjects=frozenset({"sam"})))
    agent = run.agent(call("mail__send", "c1", text="hi"))
    paused = await agent.run("Mail them")
    assert isinstance(paused.output, DeferredToolRequests)
    again = await agent.run(
        message_history=paused.all_messages(),
        deferred_tool_results=DeferredToolResults(
            approvals={"c1": True}, metadata={"c1": {APPROVAL: 7}}
        ),
    )
    assert isinstance(again.output, DeferredToolRequests)
    assert again.output.metadata["c1"][APPROVAL] == "apr_2"


async def test_two_capabilities_of_one_tool_name_are_refused() -> None:
    run = Run(capability("a.b.c"), capability("a.b__c"))
    with pytest.raises(ValueError, match="two capabilities are the tool a__b__c"):
        await run.agent(say("Never.")).run("Go")
