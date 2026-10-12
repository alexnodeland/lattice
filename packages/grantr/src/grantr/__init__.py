"""grantr: identity and access for artifactr and reflexr.

Tenants, their members, groups, roles and service principals, and the grants that bind them to
tenants, workspaces, threads, artifacts and rules. The libraries ask it, through their own hooks,
before every command and read; it imports neither library, and neither imports it.

It is planned, and holds only its version so far. Its documentation, with its decisions and the
plan that builds it, is at <https://lattice.alexnodeland.com/grantr/>.
"""

from importlib.metadata import version

__version__ = version("grantr")

__all__ = ["__version__"]
