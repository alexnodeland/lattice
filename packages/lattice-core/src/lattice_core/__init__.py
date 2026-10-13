"""lattice-core: what lattice's packages share, and must keep identical.

A package that needs one of these helpers depends on lattice-core, and re-exports what it makes
public, so an application imports from the package it uses. lattice-core imports no lattice
package (lattice ADR-0018).

- :mod:`lattice_core.schema`: JSON Schema helpers for Pydantic models, such as
  :func:`~lattice_core.schema.tag_required`.
- :mod:`lattice_core.text`: checks on text before it is stored, such as
  :func:`~lattice_core.text.holds_nul`.
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__ = version("lattice-core-ai")
"""The installed distribution's version."""
