"""What a quick read of the agent's code finds, for the person who approves it: advisory only.

The code is parsed, never run, and walked for what most often reaches past the app: modules with
the process, the file system or the network in them, the builtins that run or open anything, a
dunder that climbs out of an object, a name looked up at run time, a loop with no end, and a
character the reader doesn't see. It is not a sandbox and can't be one: an alias, a module the
app already imported, code built as a string and handed to the app, and the app's own modules
(`FreeCAD`, `bpy`), which open files and reach the system, pass it unseen (ADR-0085). The
approval is the gate; this only helps the person read.
"""

import ast
import re
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


HIDDEN: Final = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\xad\u061c\u180e\u200b-\u200f\u2028-\u202e"
    "\u2060-\u2064\u2066-\u2069\ufe00-\ufe0f\ufeff\ud800-\udfff\U000e0000-\U000e007f"
    "\U000e0100-\U000e01ef]"
)
"""Characters a reader doesn't see as they run: controls, separators, soft hyphens, zero-width,
direction-changing and tag characters, variation selectors, and lone surrogates, which no
encoding takes. portalr's approval card shows the same ones as their code points."""


def scan(code: str) -> list[str]:
    """What the code holds that reaches past the app, or hides, each a line for the approver."""
    hidden = [
        f"line {code.count(chr(10), 0, m.start()) + 1}: holds an unseen character, "
        f"U+{ord(m.group()):04X}"
        for m in HIDDEN.finditer(code)
    ]
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        where = f"line {error.lineno}: " if error.lineno else ""
        return [*hidden, f"{where}it isn't Python that parses ({error.msg})"]
    except (ValueError, RecursionError, MemoryError) as error:
        return [*hidden, f"it can't be analysed ({type(error).__name__})"]
    found = {
        (getattr(node, "lineno", 0), finding)
        for node in ast.walk(tree)
        if (finding := _finding(node)) is not None
    }
    return [*hidden, *(f"line {line}: {finding}" for line, finding in sorted(found))]


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
