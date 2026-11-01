"""The platform contracts' JSON Schemas, printed for the files checked in at ``schemas/``.

Each contract of lattice RFC-0011 publishes a JSON Schema, named by its major version, such as
``schemas/capabilities.v1.json``. A test fails if one drifts from its models. Regenerate them
with ``moon run lattice-core:schema``, which runs, for each::

    python -m lattice_core.contracts capabilities > schemas/capabilities.v1.json
"""

import json
import sys
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final

from pydantic import JsonValue

from lattice_core import adapters, approvals, bindings, capabilities, egress, secrets

__all__ = ["SCHEMAS", "main"]

SCHEMAS: Final[Mapping[str, Callable[[], dict[str, JsonValue]]]] = MappingProxyType(
    {
        "adapters": adapters.contract_schema,
        "approvals": approvals.contract_schema,
        "bindings": bindings.contract_schema,
        "capabilities": capabilities.contract_schema,
        "egress": egress.contract_schema,
        "secrets": secrets.contract_schema,
    }
)
"""Each contract's JSON Schema, by the contract's name."""


def main(argv: list[str] | None = None) -> None:
    """Write the JSON Schema of the contract named on the command line to standard output.

    Raises:
        SystemExit: If no contract, or one it doesn't know, is named.
    """
    names = sys.argv[1:] if argv is None else argv
    if len(names) != 1 or names[0] not in SCHEMAS:
        raise SystemExit(f"usage: python -m lattice_core.contracts {{{','.join(SCHEMAS)}}}")
    sys.stdout.write(json.dumps(SCHEMAS[names[0]](), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
