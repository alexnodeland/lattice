"""DeckCraft's adapter: `.pptx` decks edited by DeckCraft's own commands, run headless.

[`Subprocess`][artifactr.files.deckcraft.Subprocess] spawns DeckCraft's CLI on this machine, a
fresh MCP server on stdio for every call, for tests and trusted files: its CLI confines nothing,
so it is spawned only with `trusted=True` (native files ADR-0009). The fingerprint is read from
the file itself, by [`fingerprint`][artifactr.files.deckcraft.fingerprint]: the digest of its
parts (lattice RFC-0003, phase 2).
"""

from artifactr.files.deckcraft.headless import Subprocess
from artifactr.files.deckcraft.pptx import fingerprint, media_type, outline, text

__all__ = ["Subprocess", "fingerprint", "media_type", "outline", "text"]
