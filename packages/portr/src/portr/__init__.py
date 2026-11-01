"""portr: one gateway that serves lattice's commands to outside clients.

People connect Claude, ChatGPT, Cursor and other clients over MCP (and, for coding agents, ACP),
and every call goes through lattice-core's enforcer, so a client acting for a person does what
the person may, and asks them what they would be asked (lattice RFC-0014). portr reaches the
libraries' commands only through lattice-core's registry: it imports no library.

[`portr.core`][portr.core] makes what a client is offered from the composed commands. Its
documentation, with its decisions and the plan that builds the rest, is at
<https://lattice.alexnodeland.com/portr/>.
"""

from importlib.metadata import version

__version__ = version("portr-ai")

__all__ = ["__version__"]
