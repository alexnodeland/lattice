"""Score configs through the ``ScoreConfigStore`` port: creating the ones a store lacks."""

from collections.abc import Iterable

from evalr.core.fields import ScoreConfig
from evalr.core.ports import ScoreConfigStore

__all__ = ["sync_score_configs"]


async def sync_score_configs(store: ScoreConfigStore, configs: Iterable[ScoreConfig]) -> list[str]:
    """Create the configs whose names a store does not have yet.

    A config the store has by name is left as it is, even if its definition differs, so a
    backend's links from scores to configs never break::

        await sync_score_configs(store, score_configs(Helpfulness))

    Args:
        store: Where the configs live.
        configs: The configs to have, such as ``score_configs`` of each verdict or feedback type.

    Returns:
        The names of the configs created, in the order given. A name given twice is created once.
    """
    existing = set(await store.names())
    created: list[str] = []
    for config in configs:
        if config.name not in existing:
            await store.create(config)
            existing.add(config.name)
            created.append(config.name)
    return created
