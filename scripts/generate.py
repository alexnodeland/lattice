"""Run a generator module and write what it prints to a file: only what it prints.

Usage: scripts/generate.py OUTPUT MODULE [ARGUMENT...]

The `schema` tasks regenerate committed files (JSON Schemas, OpenAPI documents) from modules
that print them. Redirecting the task's whole standard output, as `uv run python -m MODULE >
OUTPUT` did, also caught whatever the tools in front of Python printed first: in an AI agent's
shell, proto's shim for `uv` prints an NDJSON notice ("Detected an AI agent environment, ...")
on stdout, and it landed at the top of the generated files. This runs inside Python, as `uv run
python scripts/generate.py ...`, so it takes only the module's own output: the module runs as
`python -m MODULE ARGUMENT...` would, with its standard output captured, and OUTPUT is written
once the module has finished. A module that fails leaves OUTPUT as it was.
"""

import contextlib
import io
import runpy
import sys
from pathlib import Path


def generate(output: Path, module: str, arguments: list[str]) -> None:
    """Run `module` as `__main__` with `arguments`, and write what it printed to `output`."""
    printed = io.StringIO()
    argv = sys.argv
    sys.argv = [module, *arguments]
    try:
        with contextlib.redirect_stdout(printed):
            runpy.run_module(module, run_name="__main__", alter_sys=True)
    finally:
        sys.argv = argv
    output.write_text(printed.getvalue())


def main() -> None:
    """Parse the command line and generate."""
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    generate(Path(sys.argv[1]), sys.argv[2], sys.argv[3:])


if __name__ == "__main__":
    main()
