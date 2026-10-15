"""Models over a LiteLLM proxy: the ``litellm`` extra."""

from collections.abc import Sequence
from typing import Final, cast

import httpx2
from opentelemetry import context
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.settings import ModelSettings

__all__ = ["add_propagated_tags", "litellm_model"]

_PROPAGATED_TAGS: Final = "langfuse.propagated.tags"
"""The key Langfuse's ``propagate_attributes(tags=...)`` keeps a trace's tags under in
OpenTelemetry's context (langfuse 4). The Langfuse SDK has no public getter for it; a test of the
libraries' gateways sets the tags with ``propagate_attributes`` and reads them back, so an SDK
that renames the key fails there."""


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


def add_propagated_tags(tags: Sequence[str]) -> list[str]:
    """Return ``tags`` and the trace tags Langfuse is propagating in the current context.

    A run or turn's Langfuse tags, such as ``rule:<name>``, ``chain:<id>`` or ``thread:<id>``
    (lattice ADR-0022), reach LiteLLM's spend and logs this way, whichever package set them. A tag
    already in ``tags`` is not added again, so the request lists each once, in order: ``tags``,
    then the propagated tags in the order Langfuse holds them. Without Langfuse, or outside a
    ``propagate_attributes`` block, it returns ``tags``.

    Args:
        tags: The tags a request carries already.
    """
    propagated = context.get_value(_PROPAGATED_TAGS)
    held = cast("list[object]", propagated) if isinstance(propagated, list) else []
    return list(dict.fromkeys([*tags, *(tag for tag in held if isinstance(tag, str))]))
