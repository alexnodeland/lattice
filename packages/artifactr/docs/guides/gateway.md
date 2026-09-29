# The LLM gateway

Applications route their agents through a [LiteLLM](https://docs.litellm.ai/) proxy, which owns model routing (groups, fallbacks, load balancing), budgets, rate limits and guardrails ([ADR-0031](../adr/0031-litellm-proxy-first.md)). stackr runs the proxy. The `litellm` extra connects artifactr to it through pydantic-ai's LiteLLM provider, with no dependency on the litellm package ([ADR-0043](../adr/0043-the-litellm-adapter.md)).

## A model over the proxy

```python
from artifactr.litellm import LiteLLMGateway, litellm_model

agent = Agent(
    litellm_model("claude-sonnet", api_base="http://litellm:4000", api_key=proxy_key),
    deps_type=Session[AppDeps],
    capabilities=[
        ArtifactWorkspace(types=[Doc, Plan]),
        LiteLLMGateway(tenant_key=tenant_key, guardrails=guardrails, tags=["docplan"]),
    ],
)
```

`litellm_model` names one of the proxy's model groups; which provider and model serve it, and what happens when one fails, is the proxy's configuration.

## What each request carries

`LiteLLMGateway` adds to every model request of a run:

| Where | What | Used by LiteLLM for |
|---|---|---|
| `metadata.tenant_id`, `workspace_id`, `thread_id`, `run_id` | artifactr's ids | Spend and logs by tenant and workspace |
| `metadata.tags` | `artifactr`, `tenant:<id>`, `workspace:<id>`, and yours | Tag-based spend tracking and routing |
| `metadata.session_id`, `trace_user_id` | The thread, and the person who asked | Sessions and users in its Langfuse logging |
| `metadata.existing_trace_id`, and the `traceparent` header | The turn's trace | Joining the turn's trace in Langfuse and OpenTelemetry |
| `guardrails` | The workspace's guardrails | Which guardrails check the request |
| `Authorization` | The tenant's key | Budgets, rate limits and allowed models per tenant |

## Tenants and keys

Each tenant is a LiteLLM team with its own virtual keys, budgets and rate limits. The gateway asks your application for a tenant's key on each request; keep keys in your secret store:

```python
async def tenant_key(tenant_id: str) -> str | None:
    return await secrets.get(f"litellm/{tenant_id}")  # None: use the model's own key
```

artifactr never records keys: not in the log, not on spans. Keep HTTP header capture off in your OpenTelemetry instrumentation, which is its default.

## Guardrails

A workspace's policy names the guardrails its requests use, as the proxy configures them:

```python
async def guardrails(tenant_id: str, workspace_id: str) -> list[str]:
    return ["presidio-pii", "prompt-injection"] if await is_regulated(tenant_id) else []
```

When a guardrail blocks a request, the proxy answers HTTP 400. The gateway turns that into a `GuardrailBlocked` error, a `RunFailure` ([ADR-0042](../adr/0042-typed-run-failures.md)). The run ends `failed` with the reason `guardrail_blocked`, and a message that names the guardrail but never repeats what was blocked:

```json
{"type": "run_ended", "status": "failed", "reason": "guardrail_blocked",
 "error": "The model request was blocked by the presidio-pii guardrail."}
```

The request is not retried, and the `artifactr.runs` metric counts it by reason, so the Agent and LLM dashboard shows guardrail blocks beside other failures.

## Testing

The gateway works with any pydantic-ai model, so the patterns in [Testing your application](testing.md) apply. To test against the proxy's wire format without a proxy, give `litellm_model` an `httpx2.AsyncClient` over an `httpx2.MockTransport` that answers chat completions, as artifactr's own tests do.
