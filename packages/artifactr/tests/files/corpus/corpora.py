"""Each crafting app's corpus, by app: what its fidelity report opens and saves.

Nightly's fidelity job runs one app of `CORPORA` each, and a test holds its list to these.
"""

from typing import Final

from tests.files.corpus.cadcraft.corpus import CORPUS as CADCRAFT
from tests.files.corpus.designcraft.corpus import CORPUS as DESIGNCRAFT
from tests.files.corpus.figcraft.corpus import CORPUS as FIGCRAFT
from tests.files.corpus.harness import Corpus
from tests.files.corpus.photocraft.corpus import CORPUS as PHOTOCRAFT
from tests.files.corpus.vectorcraft.corpus import CORPUS as VECTORCRAFT
from tests.files.corpus.wordcraft.corpus import CORPUS as WORDCRAFT

CORPORA: Final[dict[str, Corpus]] = {
    corpus.app: corpus
    for corpus in (WORDCRAFT, CADCRAFT, PHOTOCRAFT, VECTORCRAFT, DESIGNCRAFT, FIGCRAFT)
}
