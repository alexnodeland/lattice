"""Models over a LiteLLM proxy: the ``litellm`` extra."""

import httpx2
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.settings import ModelSettings

__all__ = ["litellm_model"]


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
