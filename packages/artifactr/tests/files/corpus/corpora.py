"""Each crafting app's corpus, by app: what its fidelity report opens and saves.

Nightly's fidelity job runs one app of `CORPORA` each, and a test holds its list to these.
"""

from typing import Final

from tests.files.corpus.cadcraft.corpus import CORPUS as CADCRAFT
from tests.files.corpus.deckcraft.corpus import CORPUS as DECKCRAFT
from tests.files.corpus.designcraft.corpus import CORPUS as DESIGNCRAFT
from tests.files.corpus.effectcraft.corpus import CORPUS as EFFECTCRAFT
from tests.files.corpus.figcraft.corpus import CORPUS as FIGCRAFT
from tests.files.corpus.filmcraft.corpus import CORPUS as FILMCRAFT
from tests.files.corpus.freecad.corpus import CORPUS as FREECAD
from tests.files.corpus.gridcraft.corpus import CORPUS as GRIDCRAFT
from tests.files.corpus.harness import Corpus
from tests.files.corpus.pdfcraft.corpus import CORPUS as PDFCRAFT
from tests.files.corpus.photocraft.corpus import CORPUS as PHOTOCRAFT
from tests.files.corpus.soundcraft.corpus import CORPUS as SOUNDCRAFT
from tests.files.corpus.vectorcraft.corpus import CORPUS as VECTORCRAFT
from tests.files.corpus.wordcraft.corpus import CORPUS as WORDCRAFT

CORPORA: Final[dict[str, Corpus]] = {
    corpus.app: corpus
    for corpus in (
        *(WORDCRAFT, GRIDCRAFT, DECKCRAFT, PDFCRAFT),
        *(CADCRAFT, PHOTOCRAFT, VECTORCRAFT, DESIGNCRAFT, FIGCRAFT, FREECAD),
        *(FILMCRAFT, EFFECTCRAFT, SOUNDCRAFT),
    )
}
