"""relayr: the bridge between artifactr and reflexr.

Events from chats and artifacts become events for rules, and runs act back in the chat as
proposals and notices. relayr uses only the two libraries' public APIs, and neither library
imports it or the other.

See `docs/architecture.md` for the design.
"""

from importlib.metadata import version

__version__ = version("relayr")

__all__ = ["__version__"]
