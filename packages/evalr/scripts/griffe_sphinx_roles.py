"""A Griffe extension that turns reStructuredText idioms in docstrings into Markdown.

evalr's docstrings follow the Google style, but a few of them use two reStructuredText idioms
that the API reference, which renders docstrings as Markdown, would show literally:

- **Sphinx roles**, such as ``:class:`Dataset``` or ``:meth:`~evalr.core.Dataset.split```. Each
  becomes a Markdown cross-reference (``[Dataset][evalr.core.Dataset]``), resolved in the scope
  of the object whose docstring contains it. A role whose target cannot be resolved, or a module
  role naming an internal module, becomes inline code instead of a broken link.
- **Literal-block markers**: a paragraph ending in ``::`` introduces an indented code block. The
  marker becomes a single colon (or disappears, when it stands alone), and the indented block
  that follows renders as code in Markdown too.

The library's docstrings stay as they are.
"""

import re
from typing import Any

import griffe

_ROLE = re.compile(
    r":(?P<role>class|meth|func|mod|attr|data|exc|obj):`(?P<tilde>~?)(?P<target>[\w.]+)`"
)

# A paragraph's closing "::" (after text), or one on a line of its own.
_LITERAL_AFTER_TEXT = re.compile(r"(?m)(?<=\S)::$")
_LITERAL_ALONE = re.compile(r"(?m)^[ \t]*::[ \t]*\n")

# The modules the reference renders a page for; other modules are internal.
_PUBLIC_MODULES = frozenset(
    {
        "evalr",
        "evalr.core",
        "evalr.memory",
        "evalr.contracts",
        "evalr.jsonl",
        "evalr.dspy",
        "evalr.decision",
        "evalr.langfuse",
        "evalr.hf",
        "evalr.measures",
        "evalr.online",
    }
)


class SphinxRoles(griffe.Extension):
    """Rewrite roles and literal-block markers in every docstring of a package once loaded."""

    def on_package(self, *, pkg: griffe.Module, **_kwargs: Any) -> None:
        """Rewrite the package's docstrings."""
        _rewrite(pkg, seen=set())


def _rewrite(obj: griffe.Object, *, seen: set[str]) -> None:
    if obj.path in seen:
        return
    seen.add(obj.path)
    if obj.docstring is not None:
        text = _ROLE.sub(lambda match: _reference(obj, match), obj.docstring.value)
        text = _LITERAL_ALONE.sub("", _LITERAL_AFTER_TEXT.sub(":", text))
        obj.docstring.value = text
    for member in obj.members.values():
        if isinstance(member, griffe.Object):  # aliases are documented where they are defined
            _rewrite(member, seen=seen)


def _reference(obj: griffe.Object, match: re.Match[str]) -> str:
    target = match["target"]
    label = target.rsplit(".", 1)[-1] if match["tilde"] else target
    path = _resolve(obj, target)
    if path is None or (match["role"] == "mod" and path not in _PUBLIC_MODULES):
        return f"`{label}`"
    return f"[`{label}`][{path}]"


def _resolve(obj: griffe.Object, target: str) -> str | None:
    """Resolve a possibly dotted name in the object's scope, as Sphinx would."""
    if target.startswith("evalr."):
        return target
    first, _, rest = target.partition(".")
    try:
        resolved = obj.resolve(first)  # looks in the object's scope, then its parents'
    except griffe.NameResolutionError:
        return None
    return f"{resolved}.{rest}" if rest else resolved
