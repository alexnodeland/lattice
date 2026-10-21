"""Write the default kit's stylesheet: ``python -m portalr.brand <tokens.css>``."""

import sys
from pathlib import Path

from portalr.brand import compile_kit


def main(argv: list[str]) -> None:
    """Write the default kit's stylesheet to the one path given."""
    if len(argv) != 2:
        sys.exit("usage: python -m portalr.brand <tokens.css>")
    Path(argv[1]).write_text(compile_kit())


if __name__ == "__main__":
    main(sys.argv)
