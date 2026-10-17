"""The tools [`TrackerCapability`][relayr.trackers.TrackerCapability] gives an agent.

An agent names an item by the key it filed it by, which the ledger maps to the item.
"""

from typing import Any

from pydantic_ai import FunctionToolset, ModelRetry, RunContext

from reflexr.workspace import Reaction
from relayr.outbound import NotAllowed
from relayr.trackers.actions import Deleted, TrackerActions, TrackerRefused, Trackers
from relayr.trackers.port import ItemDraft, ItemRef, Priority, State

# Tools annotate their context as RunContext[...] literally: pydantic-ai detects context-taking
# tools by that annotation, and a type alias would hide it.


def tracker_tools(trackers: Trackers) -> FunctionToolset[Reaction[Any]]:
    """Build the tools for writing to the workspace's tracker through `trackers`."""
    toolset = FunctionToolset[Reaction[Any]]()

    @toolset.tool
    async def file_item(
        ctx: RunContext[Reaction[Any]],
        key: str,
        title: str,
        description: str = "",
        priority: Priority | None = None,
        labels: list[str] | None = None,
    ) -> str:
        """File an item in the tracker, or find the one filed by the same key before.

        Args:
            key: What the item is filed by: the same key always names the same item, such as
                `incident/<id>`.
            title: Its title.
            description: Its body, as HTML.
            priority: How urgent it is.
            labels: Label names.
        """
        draft = ItemDraft(
            title=title, description=description, priority=priority, labels=tuple(labels or ())
        )
        acting = trackers.acting(ctx.deps)
        try:
            filed = await acting.ensure_item(draft, key=key)
            if isinstance(filed, Deleted):
                return f"A person deleted the item {key} filed; it isn't filed again."
            return f"Filed as {filed.name}: {await acting.link(filed)}"
        except (NotAllowed, TrackerRefused) as refused:
            raise ModelRetry(str(refused)) from refused

    @toolset.tool
    async def comment_on_item(ctx: RunContext[Reaction[Any]], key: str, body: str) -> str:
        """Comment on the item filed by a key.

        Args:
            key: The key the item was filed by.
            body: What the comment says, as HTML.
        """
        acting = trackers.acting(ctx.deps)
        try:
            await acting.comment(await _filed(acting, key), body)
        except (NotAllowed, TrackerRefused) as refused:
            raise ModelRetry(str(refused)) from refused
        return "Done."

    @toolset.tool
    async def set_item_state(ctx: RunContext[Reaction[Any]], key: str, state: State) -> str:
        """Move the item filed by a key to a state.

        Args:
            key: The key the item was filed by.
            state: Where it goes.
        """
        acting = trackers.acting(ctx.deps)
        try:
            await acting.set_state(await _filed(acting, key), state)
        except (NotAllowed, TrackerRefused) as refused:
            raise ModelRetry(str(refused)) from refused
        return "Done."

    @toolset.tool
    async def read_item(ctx: RunContext[Reaction[Any]], key: str) -> str:
        """Read the item filed by a key: its title, body, state, priority and labels, as JSON.

        Args:
            key: The key the item was filed by.
        """
        acting = trackers.acting(ctx.deps)
        try:
            item = await acting.read(await _filed(acting, key))
        except (NotAllowed, TrackerRefused) as refused:
            raise ModelRetry(str(refused)) from refused
        if item is None:
            raise ModelRetry(f"the item {key} filed was deleted")
        return item.model_dump_json(include={"title", "description", "state", "priority", "labels"})

    return toolset


async def _filed(acting: TrackerActions, key: str) -> ItemRef:
    filed = await acting.filed(key)
    if filed is None:
        raise ModelRetry(f"no item is filed by {key}; file one first")
    return filed
