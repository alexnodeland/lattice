"""admin names every setting lattice-core declares by what it limits, never by its key.

A connected app vetted later adds its `connect-per-hour:<app>` to the registry; without a label in
admin's `LABELS`, its field would be named by the registry's sentence (portalr ADR-0067).
"""

import re
from pathlib import Path

from artifactr.workspace import DIRECT_WRITES
from lattice_core.settings import KNOWN_SETTINGS

SETTINGS_TS = Path(__file__).parents[1] / "packages/portalr/web/admin/src/settings.ts"


def test_every_declared_setting_has_a_label_in_admin() -> None:
    source = SETTINGS_TS.read_text()
    table = source[source.index("const LABELS") :]
    table = table[: table.index("};")]
    labelled = set(re.findall(r'"([a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)?)":', table))
    # And artifactr's, which each application declares over its own kinds (ADR-0009).
    assert labelled == {*KNOWN_SETTINGS, DIRECT_WRITES}, "add each setting's label to LABELS"
