"""lattice's integrations as the UIs read them before grantr answers: key, default and sentence.

``python -m portalr.integrations`` prints lattice-core's registry, ``KNOWN``, as JSON, in its
order; ``moon run portalr:schema`` writes it to ``schemas/integrations.json``, which a test holds to
the registry, and the client's types are generated from it. The app falls back to each key's
default when it can't read a workspace's integrations (portalr ADR-0045).
"""

import json
import sys

from lattice_core.integrations import KNOWN


def registry_document() -> list[dict[str, str | bool]]:
    """Each integration of lattice's registry, in its order: its key, default and description."""
    return [
        {"key": known.key, "default": known.default, "description": known.description}
        for known in KNOWN.values()
    ]


def main() -> None:
    """Write the document to standard output."""
    sys.stdout.write(json.dumps(registry_document(), indent=2) + "\n")


if __name__ == "__main__":
    main()
