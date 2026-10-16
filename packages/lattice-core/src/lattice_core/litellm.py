"""Models over a LiteLLM proxy: the ``litellm`` extra."""

from collections.abc import Sequence
from typing import Final, cast

import httpx2
from opentelemetry import context
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.litellm import LiteLLMProvider
from pydantic_ai.settings import ModelSettings

__all__ = ["PROPAGATED_TAG_PREFIXES", "add_propagated_tags", "litellm_model"]

_PROPAGATED_TAGS: Final = "langfuse.propagated.tags"
"""The key Langfuse's ``propagate_attributes(tags=...)`` keeps a trace's tags under in
OpenTelemetry's context. It is Langfuse's internal one, built by ``_get_propagated_context_key``
in ``langfuse/_client/propagation.py`` (the SDK has no public getter), and verified in the version
the lockfile holds, langfuse 4.16.0, of the supported range. The libraries' gateway tests set tags
with ``propagate_attributes`` and read them in the request, so a release that renames the key
fails there (lattice ADR-0022)."""

PROPAGATED_TAG_PREFIXES: Final = ("rule:", "kind:")
"""The kinds of trace tag that reach LiteLLM: a rule's name and an artifact's kind, which are as
many as the application defines. ``thread:`` and ``chain:`` tags stay in Langfuse, since each
thread and each chain would add a row to LiteLLM's tag spend per day, without bound; a thread's
cost is read from Langfuse's session. ``tenant:`` and ``workspace:`` are in a request already."""


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
    """Return ``tags`` and the bounded trace tags Langfuse is propagating in the current context.

    The trace tags whose prefix is in :data:`PROPAGATED_TAG_PREFIXES`, such as ``rule:<name>`` or
    ``kind:<artifact kind>``, reach LiteLLM's spend and logs this way, whichever package set them
    (lattice ADR-0022). A tag already in ``tags`` is not added again, so the request lists each
    once, in order: ``tags``, then the propagated tags in the order Langfuse holds them. Without
    Langfuse, or outside a ``propagate_attributes`` block, it returns ``tags``.

    Args:
        tags: The tags a request carries already.
    """
    propagated = context.get_value(_PROPAGATED_TAGS)
    held = cast("list[object]", propagated) if isinstance(propagated, list) else []
    extra = (
        tag for tag in held if isinstance(tag, str) and tag.startswith(PROPAGATED_TAG_PREFIXES)
    )
    return list(dict.fromkeys([*tags, *extra]))
