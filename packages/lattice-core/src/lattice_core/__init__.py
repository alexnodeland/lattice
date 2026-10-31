"""lattice-core: what lattice's packages share, and must keep identical.

A package that needs one of these helpers depends on lattice-core, and re-exports what it makes
public, so an application imports from the package it uses. lattice-core imports no lattice
package (lattice ADR-0018).

- :mod:`lattice_core.schema`: JSON Schema helpers for Pydantic models, such as
  :func:`~lattice_core.schema.tag_required`.
- :mod:`lattice_core.integrations`: the registry of integrations, and the port that says whether
  one is on in a workspace.
- :mod:`lattice_core.tags`: the tags that file a model request's spend under its tenant and
  workspace.
- :mod:`lattice_core.text`: checks on text before it is stored, such as
  :func:`~lattice_core.text.holds_nul`.
- :mod:`lattice_core.origins`: web origins as a browser compares them, such as
  :func:`~lattice_core.origins.web_origin`, for the settings that name a portal, its mini apps'
  sandbox and its editors.
- :mod:`lattice_core.sql`: SQL helpers for storage on SQLAlchemy's asyncio API, behind the
  ``sql`` extra.
- :mod:`lattice_core.otel`: OpenTelemetry in one call, behind the ``otel`` extra, and the
  contract a library's contribution follows, which needs none.
- :mod:`lattice_core.langfuse`: a Langfuse client's span filters, behind the ``langfuse`` extra.
- :mod:`lattice_core.litellm`: a model over a LiteLLM proxy, behind the ``litellm`` extra.
- :mod:`lattice_core.logs`: logging left as the application configured it.
- :mod:`lattice_core.refusals`: the refused body and responses a REST router documents.
- :mod:`lattice_core.capabilities`: the capability registry's contract: capabilities, the
  providers that offer them, the context a call carries, and the registry that composes them
  (lattice RFC-0011).
- :mod:`lattice_core.approvals`: the approval contract: one call asked of the people who may
  answer it, bound to its arguments, and the ports a store, a policy and a surface implement.
- :mod:`lattice_core.secrets`: the secrets contract: references kept everywhere, values read
  only within their owner, and the port a store implements.
- :mod:`lattice_core.egress`: the egress policy, as pure functions: whether a call may go out
  under a purpose, and to which checked address.
- :mod:`lattice_core.adapters`: what answers a port in a deployment, how it is found, and the
  port versions it implements.
- :mod:`lattice_core.taint`: whether a turn, a run or a session has read untrusted content.
- :mod:`lattice_core.contracts`: the platform contracts' JSON Schemas.
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__ = version("lattice-core-ai")
"""The installed distribution's version."""
