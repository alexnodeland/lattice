"""lattice-core: what lattice's libraries share, and must keep identical.

artifactr, reflexr, grantr and relayr never import one another (reflexr ADR-0003), but some of
their infrastructure is the same code, and must stay the same: it lives here, once, and each
library depends on it and re-exports what it makes public (lattice ADR-0018). Nothing about any
library's domain belongs here.

- :mod:`lattice_core.schema`: JSON Schema helpers for Pydantic models, such as
  :func:`~lattice_core.schema.tag_required`.
- :mod:`lattice_core.text`: checks on the text the libraries store, such as
  :func:`~lattice_core.text.holds_nul`.
"""

from importlib.metadata import version

__version__ = version("lattice-core-ai")
"""The installed distribution's version."""
