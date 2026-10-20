"""Each crafting app's corpus, by app: what its fidelity report opens and saves.

Nightly's fidelity job runs one app of `CORPORA` each, and a test holds its list to these.
"""

from typing import Final

from tests.files.corpus.deckcraft.corpus import CORPUS as DECKCRAFT
from tests.files.corpus.gridcraft.corpus import CORPUS as GRIDCRAFT
from tests.files.corpus.harness import Corpus
from tests.files.corpus.pdfcraft.corpus import CORPUS as PDFCRAFT
from tests.files.corpus.wordcraft.corpus import CORPUS as WORDCRAFT

CORPORA: Final[dict[str, Corpus]] = {
    corpus.app: corpus for corpus in (WORDCRAFT, GRIDCRAFT, DECKCRAFT, PDFCRAFT)
}
