"""Models over a LiteLLM proxy, and the tags a request carries: the ``litellm`` extra."""

from urllib.parse import quote

import httpx2
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.settings import ModelSettings

__all__ = ["litellm_model", "request_tags"]


def litellm_model(
    model: str,
    *,
    api_base: str | None = None,
    api_key: str | None = None,
    http_client: httpx2.AsyncClient | None = None,
    settings: ModelSettings | None = None,
) -> OpenAIChatModel:
    """Return a pydantic-ai model that calls a LiteLLM proxy's model group.

    Routing, fallbacks, budgets and guardrails are the proxy's configuration; the model only
    names the group.

    Args:
        model: The proxy's model group, such as ``claude-sonnet``.
        api_base: The proxy's URL, such as ``http://litellm:4000``. Defaults to the provider's
            environment variables.
        api_key: The proxy key used when a request carries no tenant's key.
        http_client: The HTTP client, for tests or a shared connection pool.
        settings: The model's default settings, as every pydantic-ai model takes them, such as
            a ``temperature``. An agent's or a run's ``model_settings`` override them key by
            key.
    """
    if http_client is None:
        provider = LiteLLMProvider(api_key=api_key, api_base=api_base)
    else:
        provider = LiteLLMProvider(api_key=api_key, api_base=api_base, http_client=http_client)
    return OpenAIChatModel(model, provider=provider, settings=settings)


def request_tags(tenant_id: str, workspace_id: str) -> list[str]:
    """Return the tags that file a model request's spend under its tenant and its workspace.

    LiteLLM adds up each tag's spend across every request that carries it, whichever tenant made
    it. Workspace ids are each tenant's own, so ``workspace:<id>`` alone mixes tenants whose
    workspaces share an id. ``tenant-workspace:<tenant>/<workspace>`` names one tenant's
    workspace; each id in it is percent-encoded, every character but letters, digits and
    ``-._~``, so the ``/`` between them can't be either's, and no comma splits the tag where
    LiteLLM's tag queries split their lists. The tags are, in order:

    - ``tenant:<tenant id>``
    - ``workspace:<workspace id>``
    - ``tenant-workspace:<percent-encoded tenant id>/<percent-encoded workspace id>``
    """
    pair = f"{quote(tenant_id, safe='')}/{quote(workspace_id, safe='')}"
    return [f"tenant:{tenant_id}", f"workspace:{workspace_id}", f"tenant-workspace:{pair}"]
