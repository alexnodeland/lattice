"""Each corpus: one file per feature, as its maker makes it, each holding its feature; and the
nightly fidelity job runs every corpus."""

from pathlib import Path

import pytest
import yaml

from artifactr.files.craft import CRAFTS
from tests.files.corpus.corpora import CORPORA
from tests.files.corpus.harness import GIVEN, PINS, Corpus

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


def test_an_app_on_by_default_has_a_corpus_its_hostile_files_and_a_nightly_run() -> None:
    """The gate an app passes before its key is on by default (native files ADR-0011)."""
    on = {name for name, craft in CRAFTS.items() if craft.integration.default}
    assert on <= set(CORPORA)
    assert all(set(GIVEN) < set(CORPORA[app].hostile_names()) for app in on), "a format's own"


@pytest.mark.parametrize("corpus", CORPORA.values(), ids=list(CORPORA))
def test_each_given_hostile_file_is_made(corpus: Corpus) -> None:
    sizes = {name: len(corpus.hostile_file(name)) for name in GIVEN}
    assert sizes["empty"] == 0
    assert all(size > 0 for name, size in sizes.items() if name != "empty")
