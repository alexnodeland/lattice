"""artifactr's catalog as a document, for ``schemas/artifactr.commands.json``.

``moon run artifactr:schema`` writes it, and a test holds it to
:data:`~artifactr.commands.CATALOG` (lattice RFC-0014).
"""

import json
import sys
from typing import Any

from artifactr.commands import CATALOG, LISTED
from lattice_core.commands import Command


def _canonical(command: Command) -> dict[str, Any]:
    """A command as JSON, its sets sorted, so the document is the same from one run to the next."""
    dumped = command.model_dump(mode="json")
    dumped["surfaces"] = sorted(dumped["surfaces"])
    dumped["capability"]["effects"] = sorted(dumped["capability"]["effects"])
    return dumped


def catalog_document() -> dict[str, Any]:
    """Every command of artifactr's catalog, by name, and each action no command gates."""
    return {
        "title": "artifactr's commands",
        "commands": {command.name: _canonical(command) for command in CATALOG.commands()},
        "listed": dict(sorted(LISTED.items())),
    }


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(catalog_document(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
