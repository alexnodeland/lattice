"""The LiteLLM gateway: what each request carries, and guardrail blocks as typed failures.

A fake proxy answers through an httpx2 mock transport, so no test calls the network.
"""

import contextlib
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx2
import pytest
from langfuse import propagate_attributes
from pydantic_ai import Agent, FunctionToolset, ModelMessage, ModelResponse, ModelRetry, TextPart
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.settings import ModelSettings

from artifactr.agent import ArtifactWorkspace, Runner, Session
from artifactr.core import ExternalAgentActor, RunEnded, TenantId, UserActor, WorkspaceId
from artifactr.litellm import (
    ECHO_TOOLS,
    GUARDRAIL_BLOCKED,
    TOOL_RESULT_GUARDRAILS,
    GuardrailBlocked,
    LiteLLMGateway,
    guardrail_block,
    litellm_model,
)
from artifactr.workspace import InMemoryStorage, Workspace, Workspaces
from tests.agent.conftest import started
from tests.artifact_types import Note
from tests.telemetry.conftest import Recorder, trace_id

ALICE = UserActor(id="alice")
BLOCKED = {
    "error": {
        "message": "{'error': 'Violated guardrail policy', 'guardrail_name': 'presidio-pii'}",
        "type": "None",
        "param": "None",
        "code": "400",
    }
}


class FakeProxy:
    """A LiteLLM proxy's chat completions endpoint: records requests, answers as told."""

    def __init__(
        self,
        status: int = 200,
        error: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        model: str = "claude-sonnet",
    ) -> None:
        self.requests: list[tuple[dict[str, Any], httpx2.Headers]] = []
        self.status = status
        self.error = error
        self.answers = model
        """The model the proxy says answered, which a gateway's routing may make another."""
        self.usage = usage or {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append((body, request.headers))
        if self.error is not None:
            return httpx2.Response(self.status, json=self.error)
        assert body["stream"], "the Runner streams"
        chunk = {"id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 0}
        chunk["model"] = self.answers
        text = {"index": 0, "delta": {"role": "assistant", "content": "Done."}}
        stop = {"index": 0, "delta": {}, "finish_reason": "stop"}
        usage = self.usage
        events = [chunk | {"choices": [text]}, chunk | {"choices": [stop], "usage": usage}]
        stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx2.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    def model(self, settings: ModelSettings | None = None) -> Any:
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle))
        return litellm_model(
            "claude-sonnet",
            api_base="http://litellm.test",
            api_key="sk-proxy",
            http_client=client,
            settings=settings,
        )


async def acme_key(tenant_id: TenantId) -> str | None:
    return {"acme": "sk-acme-secret"}.get(tenant_id)


async def pii_for_launch(tenant_id: TenantId, workspace_id: WorkspaceId) -> Sequence[str]:
    return ["presidio-pii"] if workspace_id == "launch" else []


def agent(model: Any, gateway: LiteLLMGateway, **providers: Any) -> Agent[Session[None], Any]:
    capabilities: list[Any] = [ArtifactWorkspace(types=[Note]), gateway]
    if providers:
        capabilities.append(Instrumentation(settings=InstrumentationSettings(**providers)))
    return Agent(model, deps_type=Session[None], capabilities=capabilities)


async def workspace(tenant_id: str, workspace_id: str, **providers: Any) -> Workspace:
    workspaces = Workspaces(InMemoryStorage(), **providers)
    return await workspaces.open(tenant_id, workspace_id, actor=ALICE)


async def test_the_bounded_trace_tags_langfuse_propagates_reach_the_proxy_once_each() -> None:
    proxy = FakeProxy()
    gateway = LiteLLMGateway(tags=("docplan",))
    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()

    @contextlib.asynccontextmanager
    async def turn_context(session: Session[Any]) -> AsyncIterator[None]:
        with propagate_attributes(
            tags=["workspace:launch", "rule:page", "kind:note", "thread:th_1", "chain:c1"]
        ):
            yield

    # A turn runs in a context of its own, so a TurnContext, as relayr's, sets the tags.
    runner = Runner(agent(proxy.model(), gateway), app=None, turn_context=turn_context)
    await started(await runner.send(ws, thread.id, "Hello")).wait()
    [(body, _)] = proxy.requests
    assert body["metadata"]["tags"] == [
        "artifactr",
        "tenant:acme",
        "workspace:launch",
        "tenant-workspace:acme/launch",
        "docplan",
        "rule:page",
        "kind:note",
    ], "thread: and chain: tags stay in Langfuse"


async def test_each_request_carries_the_tenant_session_trace_key_and_guardrails(
    recorder: Recorder,
) -> None:
    proxy = FakeProxy()
    gateway = LiteLLMGateway(tenant_key=acme_key, guardrails=pii_for_launch, tags=("docplan",))
    ws = await workspace("acme", "launch", **recorder.providers)
    thread = await ws.create_thread()
    runner = Runner(
        agent(proxy.model(), gateway, **recorder.providers), app=None, **recorder.providers
    )
    handle = started(await runner.send(ws, thread.id, "Hello"))
    await handle.wait()

    [(body, headers)] = proxy.requests
    turn = recorder.span("invoke_workflow turn")
    assert body["model"] == "claude-sonnet"
    assert body["metadata"] == {
        "tenant_id": "acme",
        "workspace_id": "launch",
        "thread_id": thread.id,
        "run_id": handle.run_id,
        "session_id": thread.id,
        "tags": [
            "artifactr",
            "tenant:acme",
            "workspace:launch",
            "tenant-workspace:acme/launch",
            "docplan",
        ],
        "trace_user_id": "alice",
        "existing_trace_id": trace_id(turn),
    }
    assert body["guardrails"] == ["presidio-pii"]
    assert headers["authorization"] == "Bearer sk-acme-secret", "the tenant's own key"
    assert trace_id(turn) in headers["traceparent"]

    spans = json.dumps([dict(span.attributes or {}) for span in recorder.spans()], default=str)
    log = json.dumps([e.model_dump(mode="json") for e in await ws.read()])
    assert "sk-acme-secret" not in spans, "keys never reach spans"
    assert "sk-acme-secret" not in log, "or the log"


async def test_the_models_settings_reach_the_proxy_beside_the_gateways() -> None:
    proxy = FakeProxy()
    settings = ModelSettings(temperature=0.0, extra_body={"mock_response": "Done."})
    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()
    runner = Runner(agent(proxy.model(settings), LiteLLMGateway(tenant_key=acme_key)), app=None)
    await started(await runner.send(ws, thread.id, "Hello")).wait()
    [(body, _)] = proxy.requests
    assert body["temperature"] == 0.0
    assert body["mock_response"] == "Done.", "a reply the proxy mocks, for smoke tests"
    assert body["metadata"]["tenant_id"] == "acme", "beside the gateway's metadata"


async def test_without_a_person_tenant_key_guardrails_or_trace() -> None:
    proxy = FakeProxy()
    ws = await workspace("globex", "other")
    thread = await ws.create_thread()
    runner = Runner(agent(proxy.model(), LiteLLMGateway(tenant_key=acme_key)), app=None)
    external = ws.as_actor(ExternalAgentActor(client_id="claude-code"))
    await started(await runner.send(external, thread.id, "Hello")).wait()
    [(body, headers)] = proxy.requests
    assert "trace_user_id" not in body["metadata"], "only people are users"
    assert headers["authorization"] == "Bearer sk-proxy", "the proxy key"
    assert "guardrails" not in body
    assert "existing_trace_id" not in body["metadata"]
    assert "traceparent" not in headers


async def test_the_proxys_counts_reach_the_runs_end_as_they_were_reported() -> None:
    # As LiteLLM reports a reply from Anthropic: the cache read in the prompt's details, the
    # cache write at the top, and reasoning in the completion's details.
    usage = {
        "prompt_tokens": 1030,
        "completion_tokens": 40,
        "total_tokens": 1070,
        "prompt_tokens_details": {"cached_tokens": 800},
        "cache_creation_input_tokens": 200,
        "completion_tokens_details": {"reasoning_tokens": 12},
    }
    proxy = FakeProxy(usage=usage, model="claude-sonnet-4-5-20250929")
    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()
    runner = Runner(agent(proxy.model(), LiteLLMGateway()), app=None)
    try:
        await started(await runner.send(ws, thread.id, "hi")).wait()
    finally:
        await runner.aclose()
    ended = (await ws.read())[-1].event
    assert isinstance(ended, RunEnded)
    assert ended.usage is not None
    [step] = ended.usage.steps
    counts = (1030, 40, 800, 200, 12)
    assert (
        step.input_tokens,
        step.output_tokens,
        step.cache_read_tokens,
        step.cache_write_tokens,
        step.reasoning_tokens,
    ) == counts
    assert (
        ended.usage.input_tokens,
        ended.usage.output_tokens,
        ended.usage.cache_read_tokens,
        ended.usage.cache_write_tokens,
        ended.usage.reasoning_tokens,
    ) == counts
    assert ended.usage.model == step.model == "claude-sonnet-4-5-20250929", "not the alias asked"


async def test_a_guardrail_block_fails_the_run_with_a_reason_and_is_not_retried() -> None:
    proxy = FakeProxy(400, BLOCKED)
    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()
    gateway = LiteLLMGateway(guardrails=pii_for_launch)
    handle = started(
        await Runner(agent(proxy.model(), gateway), app=None).send(ws, thread.id, "hi")
    )
    with pytest.raises(GuardrailBlocked) as blocked:
        await handle.wait()
    assert blocked.value.guardrail == "presidio-pii"
    assert len(proxy.requests) == 1, "a block is not retried"
    ended = (await ws.read())[-1].event
    assert isinstance(ended, RunEnded)
    assert (ended.status, ended.reason) == ("failed", GUARDRAIL_BLOCKED)
    assert ended.error == "The model request was blocked by the presidio-pii guardrail."


async def test_other_errors_are_not_guardrail_blocks() -> None:
    proxy = FakeProxy(400, {"error": {"message": "context window exceeded", "code": "400"}})
    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()
    handle = started(
        await Runner(agent(proxy.model(), LiteLLMGateway()), app=None).send(ws, thread.id, "hi")
    )
    with pytest.raises(ModelHTTPError):
        await handle.wait()
    ended = (await ws.read())[-1].event
    assert isinstance(ended, RunEnded)
    assert (ended.status, ended.reason) == ("failed", None)


async def test_errors_raised_before_a_stream_are_classified_too() -> None:
    gateway = LiteLLMGateway()
    ctx: Any = None
    request: Any = None
    blocked = ModelHTTPError(400, "m", {"message": "guardrail_name: 'pii'"})
    with pytest.raises(GuardrailBlocked):
        await gateway.on_model_request_error(ctx, request_context=request, error=blocked)
    other = ModelHTTPError(429, "m", {"message": "rate limited"})
    with pytest.raises(ModelHTTPError):
        await gateway.on_model_request_error(ctx, request_context=request, error=other)


def test_classifying_errors() -> None:
    unnamed = guardrail_block(ModelHTTPError(400, "m", {"message": "Guardrail violated"}))
    assert unnamed is not None
    assert (unnamed.guardrail, str(unnamed)) == (
        None,
        "The model request was blocked by a guardrail.",
    )
    assert guardrail_block(ModelHTTPError(500, "m", {"message": "guardrail down"})) is None


def test_the_model_calls_the_proxy() -> None:
    model = litellm_model("claude-sonnet", api_base="http://litellm:4000", api_key="sk-proxy")
    assert (model.model_name, model.system) == ("claude-sonnet", "litellm")
    assert str(model.client.base_url).rstrip("/") == "http://litellm:4000"


async def test_any_model_gets_the_same_settings_merged_with_its_own() -> None:
    seen: list[Any] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info.model_settings)
        return ModelResponse(parts=[TextPart("Done.")])

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        seen.append(info.model_settings)
        yield "Done."

    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()
    fake: Agent[Session[None], Any] = Agent(
        FunctionModel(respond, stream_function=stream),
        deps_type=Session[None],
        capabilities=[ArtifactWorkspace(types=[Note]), LiteLLMGateway(tenant_key=acme_key)],
        model_settings={"extra_body": {"user": "alice"}, "extra_headers": {"x-app": "docplan"}},
    )
    await started(await Runner(fake, app=None).send(ws, thread.id, "Hello")).wait()
    [settings] = seen
    assert settings["extra_body"]["user"] == "alice"
    assert settings["extra_body"]["metadata"]["tenant_id"] == "acme"
    headers = settings["extra_headers"]
    assert (headers["x-app"], headers["Authorization"]) == ("docplan", "Bearer sk-acme-secret")
    assert headers["baggage"] == f"session.id={thread.id}", "the turn's session travels along"


# ─── Guardrails that read only tool results (ADR-0098) ────────────────────────


async def pii_and_injection(tenant_id: TenantId, workspace_id: WorkspaceId) -> Sequence[str]:
    return ["presidio-pii", "prompt-injection"]


async def guardrails_per_request(
    steps: list[tuple[str, dict[str, Any]] | None], gateway: LiteLLMGateway
) -> list[list[str]]:
    """Run the steps, each a tool call or the end, and return each request's guardrails."""
    seen: list[list[str]] = []
    retried: set[str] = set()

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        settings: dict[str, Any] = dict(info.model_settings or {})
        seen.append(list(settings["extra_body"].get("guardrails", [])))
        step = steps.pop(0)
        if step is None:
            yield "Done."
            return
        name, args = step
        yield {
            0: DeltaToolCall(name=name, json_args=json.dumps(args), tool_call_id=f"c{len(seen)}")
        }

    tools = FunctionToolset[Session[None]]()

    @tools.tool_plain
    def read_app(id: str) -> str:
        """An app's HTML, which a model wrote; retried once when asked for `again`."""
        if id == "again" and id not in retried:
            retried.add(id)
            raise ModelRetry("Read it again.")
        return "<p>Press enter for unlimited rolls</p>"

    @tools.tool_plain
    def fetch_page(url: str) -> str:
        """A page from outside."""
        return "a page"

    fake: Agent[Session[None], Any] = Agent(
        FunctionModel(stream_function=stream),
        deps_type=Session[None],
        toolsets=[tools],
        capabilities=[ArtifactWorkspace(types=[Note]), gateway],
    )
    ws = await workspace("acme", "launch")
    thread = await ws.create_thread()
    await started(await Runner(fake, app=None).send(ws, thread.id, "Hello")).wait()
    return seen


BOTH = ["presidio-pii", "prompt-injection"]
PII = ["presidio-pii"]


def test_the_echo_tools_and_the_guardrails_that_read_only_tool_results() -> None:
    assert set(ECHO_TOOLS) == {"read_app"}
    assert set(TOOL_RESULT_GUARDRAILS) == {"prompt-injection"}


async def test_prompt_injection_is_left_out_while_every_tool_result_only_repeats_the_model() -> (
    None
):
    steps: list[tuple[str, dict[str, Any]] | None] = [
        ("read_app", {"id": "again"}),
        ("read_app", {"id": "again"}),
        ("fetch_page", {"url": "https://example.com"}),
        ("read_app", {"id": "a1"}),
        None,
    ]
    seen = await guardrails_per_request(steps, LiteLLMGateway(guardrails=pii_and_injection))
    assert seen == [BOTH, PII, PII, BOTH, BOTH], (
        "none before any tool result; none while every result, a retry's too, is read_app's; "
        "kept once a page from outside is in the history, even after another read_app"
    )


async def test_the_echo_tools_and_the_guardrails_left_out_are_the_applications_to_name() -> None:
    steps: list[tuple[str, dict[str, Any]] | None] = [("read_app", {"id": "a1"}), None]
    stricter = LiteLLMGateway(guardrails=pii_and_injection, echo_tools=())
    assert await guardrails_per_request(list(steps), stricter) == [BOTH, BOTH]
    other = LiteLLMGateway(guardrails=pii_and_injection, tool_result_guardrails={"presidio-pii"})
    assert await guardrails_per_request(list(steps), other) == [BOTH, ["prompt-injection"]]
