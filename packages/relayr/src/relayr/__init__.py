"""relayr: the bridge between artifactr and reflexr.

Events from chats and artifacts become events for rules, and runs act back in the chat as
proposals and notices. relayr uses only the two libraries' public APIs, and neither library
imports it or the other.

It is planned, and holds only its version so far. Its documentation, with its decisions and the
plan that builds it, is at <https://lattice.alexnodeland.com/relayr/>.
"""

from importlib.metadata import version

__version__ = version("relayr-ai")

__all__ = ["__version__"]
