"""The limits on every call the worker runs: its deadline, the CLI's resources, and its sizes."""

import sys
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

CONFINE: Final = Path(__file__).with_name("confine.py")
"""The launcher that sets a CLI's limits, then becomes it."""


class Limits(BaseModel):
    """What a call to the worker may take, each a typed failure when breached (lattice RFC-0003).

    The container's own limits, on memory, CPU, processes and the size of its `tmpfs`, are the
    deployment's, which stackr sets; these are the ones the worker sets on each call.
    """

    model_config = ConfigDict(frozen=True)

    edit: float = Field(default=30.0, gt=0)
    """The longest deadline, in seconds, an edit, an inspection or a lookup is given."""

    render: float = Field(default=10.0, gt=0)
    """The longest deadline, in seconds, a render is given."""

    cpu: int = Field(default=30, gt=0)
    """The CPU seconds the CLI may use, past which it is killed."""

    memory: int = Field(default=2 << 30, gt=0)
    """The address space, in bytes, the CLI may map, past which it can't allocate."""

    files: int = Field(default=256 << 20, gt=0)
    """The most bytes a file may hold: the one sent, one the CLI writes, or one inflated."""

    reply: int = Field(default=384 << 20, gt=0)
    """The most bytes a reply may hold, past which it is refused as too large."""

    def launcher(self) -> tuple[str, ...]:
        """The command a CLI is started under, to set these limits first."""
        return (
            *(sys.executable, "-I", str(CONFINE)),
            *(f"--cpu={self.cpu}", f"--memory={self.memory}", f"--files={self.files}", "--"),
        )
