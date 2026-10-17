"""A check-out: who has a native file, from which version, until when.

The lease on the artifact says that someone has it; the record says who, and what they started
from. The lease's holder is `checkout:<id>:<participant>`, which names the record, so two tabs
are two holders and a refusal can say who has the file. A check-in reads its base from here,
never from the upload.
"""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from artifactr.core import Actor, ArtifactId
from artifactr.workspace import Scope
from artifactr_files.manifest import Sha256


class Checkout(BaseModel):
    """A person's check-out of a native file."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    artifact_id: ArtifactId
    base_version: int = Field(ge=1)
    """The version checked out, which a check-in is based on."""

    base_sha256: Sha256
    """The content digest checked out, which a check-in's patch tests."""

    actor: Actor
    """Who checked it out: only they check it in or extend it."""

    expires_at: datetime
    """When the lease ends, unless it is extended."""

    checked_in: bool = False
    """Whether it was checked in, which ends it: only the same file is checked in again."""

    @property
    def holder(self) -> str:
        """The lease's holder: `checkout:<id>:<participant>`."""
        return holder_of(self.id, self.actor)


def holder_of(checkout_id: str, actor: Actor) -> str:
    """The holder of a check-out's lease, which names the check-out and who has it."""
    return f"checkout:{checkout_id}:{actor.participant}"


class Checkouts(Protocol):
    """Where check-outs are kept, by workspace and id."""

    async def save(self, scope: Scope, checkout: Checkout) -> None:
        """Keep a check-out, replacing one with its id."""
        ...

    async def get(self, scope: Scope, checkout_id: str) -> Checkout | None:
        """Return a check-out, or None."""
        ...
