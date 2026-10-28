"""The models a person may choose for a turn, as the composer's picker lists them (ADR-0086).

A message may name the model of the turn it starts (artifactr ADR-0097). Which models a workspace
allows is the application's: the closed list its gateway offers, narrowed by the workspace's
``models:allowed`` setting, which the runner's check reads too. portalr's router asks this hook,
once it has checked the caller may choose a model there, and lists what it answers. Nothing here
is a secret: a model's name, as the gateway groups it, and how the picker shows it, never where
the gateway is or a key.
"""

from collections.abc import Awaitable, Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field


class OfferedModel(BaseModel):
    """A model the picker offers."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    """The name a message gives to choose it: the gateway's model group."""

    label: str = Field(min_length=1)
    """What the picker calls it."""

    family: str = ""
    """Whose model it is, such as ``anthropic``, or ``local``; empty where unsaid."""

    local: bool = False
    """Whether it runs on the operator's own hardware: slower to its first token."""

    reasoning: bool = False
    """Whether it thinks before it answers."""


class OfferedModels(BaseModel):
    """The models a workspace allows, in the order the application lists them."""

    models: list[OfferedModel]


Models = Callable[[str, str], Awaitable[Sequence[OfferedModel]]]
"""The models a tenant's workspace allows, by tenant and workspace id: the same source the
runner's ``artifactr:use_model`` check reads, so the picker never offers what a turn refuses."""
