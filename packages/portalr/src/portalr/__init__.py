"""portalr: the portal into an application built on lattice.

An `app` UI for the people who use the application, to chat with its agents and see their
artifacts, proposals, rules and runs, and an `admin` UI for those who run it, to manage access and
see feedback, evaluations, usage and spend. portalr's Python side is a router the application
mounts beside the libraries': it serves the two UIs, and adds the few routes no library has.

Its router, ``portalr.fastapi.portalr_router``, and its readers, ``portalr.readers``, are built;
the UIs come with its plan's later phases. Its documentation, with its decisions and the plan
that builds it, is at <https://lattice.alexnodeland.com/portalr/>.
"""

from importlib.metadata import version

__version__ = version("portalr")

__all__ = ["__version__"]
