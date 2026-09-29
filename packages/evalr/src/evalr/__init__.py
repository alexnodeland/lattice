"""evalr: typed evaluation of agent systems.

An evaluator judges an input and returns a verdict: an instance of a Pydantic type, typically
one of the feedback types people also give, so evaluators can be trained on people's feedback
and measured against it.

See ``docs/architecture.md`` for the design.
"""

from importlib.metadata import version

__version__ = version("evalr")

__all__ = ["__version__"]
