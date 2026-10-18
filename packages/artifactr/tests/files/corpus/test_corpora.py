"""Each corpus: one file per feature, as its maker makes it, each holding its feature; and the
nightly fidelity job runs every corpus."""

from pathlib import Path

import pytest
import yaml

from artifactr.files.craft import CRAFTS
from tests.files.corpus.corpora import CORPORA
from tests.files.corpus.harness import PINS, Corpus

NIGHTLY = Path(__file__).parents[5] / ".github" / "workflows" / "nightly.yml"


@pytest.mark.parametrize("corpus", CORPORA.values(), ids=list(CORPORA))
def test_each_corpus_is_what_its_maker_makes(corpus: Corpus) -> None:
    files = sorted(path.name for path in corpus.folder.glob(f"*{corpus.extension}"))
    assert files == sorted(f"{feature}{corpus.extension}" for feature in corpus.makers)
    for feature, make in corpus.makers.items():
        assert corpus.source(feature) == make(), f"{feature}{corpus.extension} drifted: make it"


@pytest.mark.parametrize(
    ("corpus", "feature"),
    [(corpus, feature) for corpus in CORPORA.values() for feature in sorted(corpus.makers)],
)
def test_each_file_holds_its_feature(corpus: Corpus, feature: str) -> None:
    assert corpus.read(feature, corpus.source(feature))
    assert corpus.unsupported <= set(corpus.makers)


def test_each_corpus_is_a_pinned_crafting_apps() -> None:
    for app in CORPORA:
        assert app in CRAFTS
        assert (PINS / f"{app}.sha256").is_file()


def test_nightly_runs_the_fidelity_of_each_app_with_a_corpus() -> None:
    jobs = yaml.safe_load(NIGHTLY.read_text())["jobs"]
    assert jobs["fidelity"]["strategy"]["matrix"]["app"] == sorted(CORPORA)
