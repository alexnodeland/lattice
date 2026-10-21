"""Write the default kit's stylesheet: ``python -m portalr.brand <tokens.css>``."""

import sys
from pathlib import Path

from portalr.brand import compile_kit

if len(sys.argv) != 2:
    sys.exit("usage: python -m portalr.brand <tokens.css>")
Path(sys.argv[1]).write_text(compile_kit())
