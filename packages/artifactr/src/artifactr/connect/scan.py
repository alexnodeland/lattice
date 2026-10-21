"""What a quick read of the agent's code finds, for the person who approves it: advisory only.

The code is parsed, never run, and walked for what most often reaches past the app: modules with
the process, the file system or the network in them, the builtins that run or open anything, a
dunder that climbs out of an object, a name looked up at run time, and a loop with no end. It is
not a sandbox and can't be one: the app's own modules (`FreeCAD`, `bpy`) reach all of it, by ways
no list catches (ADR-0085). The approval is the gate; this only helps the person read.
"""

import ast
from collections.abc import Iterable
from typing import Final

__all__ = ["scan"]

MODULES: Final = frozenset(
    {
        *("os", "posix", "nt", "sys", "subprocess", "multiprocessing", "threading", "signal"),
        *("socket", "ssl", "select", "selectors", "asyncio", "http", "urllib", "ftplib"),
        *("smtplib", "requests", "httpx", "aiohttp", "webbrowser"),
        *("ctypes", "cffi", "importlib", "imp", "runpy", "pkgutil", "marshal", "pickle"),
        *("shutil", "tempfile", "pathlib", "glob", "io", "builtins", "code", "codeop"),
    }
)
"""Modules whose import is a finding: each reaches the process, the files or the network."""

CALLS: Final = frozenset(
    {"open", "eval", "exec", "compile", "__import__", "breakpoint", "input", "globals", "vars"}
)
"""Builtins whose call is a finding."""

DUNDERS: Final = frozenset(
    {
        *("__class__", "__bases__", "__mro__", "__subclasses__", "__globals__", "__builtins__"),
        *("__code__", "__closure__", "__dict__", "__getattribute__", "__loader__", "__spec__"),
    }
)
"""Attributes whose use is a finding: each climbs from an object to what it was made from."""


def scan(code: str) -> list[str]:
    """What the code holds that reaches past the app, each a line for the approver, in order."""
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return [f"line {error.lineno}: it isn't Python that parses ({error.msg})"]
    found = {
        (getattr(node, "lineno", 0), finding)
        for node in ast.walk(tree)
        if (finding := _finding(node)) is not None
    }
    return [f"line {line}: {finding}" for line, finding in sorted(found)]


def _finding(node: ast.AST) -> str | None:
    """What one node does that is a finding, if anything."""
    match node:
        case ast.Import(names=names) if bad := _modules(alias.name for alias in names):
            return f"imports {bad}"
        case ast.ImportFrom(module=str(module)) if bad := _modules([module]):
            return f"imports from {bad}"
        case ast.Call(func=ast.Name(id=name)) if name in CALLS:
            return f"calls {name}()"
        case ast.Call(func=ast.Name(id="getattr" | "setattr" | "delattr" as name), args=args) if (
            len(args) < 2 or not isinstance(args[1], ast.Constant)
        ):
            return f"calls {name}() with a name made at run time"
        case ast.Attribute(attr=attr) if attr in DUNDERS:
            return f"reaches {attr}"
        case ast.While(test=ast.Constant(value=value)) if value:
            return "loops with no end of its own"
        case _:
            return None


def _modules(names: Iterable[str]) -> str:
    """The modules among dotted names that are findings, joined, or empty."""
    return ", ".join(name for name in names if name.partition(".")[0] in MODULES)
