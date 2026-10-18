"""Each crafting app itself, run headless from its pinned CLI: its fidelity report.

Each test runs only for the app `ARTIFACTR_TEST_CRAFT` names, with its CLI in
`ARTIFACTR_TEST_CRAFT_CLI`, as `moon run artifactr:fidelity` sets them from `scripts/craft`. Each
corpus file is opened and saved, and its feature compared before and after; saving it again
must be a fixpoint. With `CRAFT_MATRIX` set, the conftest writes the results there as a Markdown
matrix (lattice RFC-0003, phase 2). Each hostile file must end in a typed failure within its
deadline (native files ADR-0011).
"""

import os

import pytest
from _pytest.mark import ParameterSet

from artifactr.files.app import App, AppFailed
from tests.files.corpus.corpora import CORPORA
from tests.files.corpus.harness import Corpus, pinned

# Two calls a test, each within its deadline, well inside the test's own timeout: a test the
# timeout ends would end the session before the conftest writes the matrix.
pytestmark = pytest.mark.timeout(120)
DEADLINE = 20


def cases() -> list[ParameterSet]:
    return [
        pytest.param(
            corpus,
            feature,
            id=f"{app}-{feature}",
            marks=[
                pytest.mark.craft(app),
                *([pytest.mark.xfail(strict=True)] if feature in corpus.unsupported else []),
            ],
        )
        for app, corpus in sorted(CORPORA.items())
        for feature in sorted(corpus.makers)
    ]


def running(corpus: Corpus) -> App:
    return corpus.adapter(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], pinned(corpus.app))


@pytest.mark.parametrize(("corpus", "feature"), cases())
async def test_an_open_and_a_save_keep_the_feature(corpus: Corpus, feature: str) -> None:
    source = corpus.source(feature)
    saved = await running(corpus).apply(source, [], deadline=DEADLINE)
    assert corpus.read(feature, saved.content) == corpus.read(feature, source)


@pytest.mark.parametrize(("corpus", "feature"), cases())
async def test_saving_twice_is_a_fixpoint(corpus: Corpus, feature: str) -> None:
    app = running(corpus)
    once = await app.apply(corpus.source(feature), [], deadline=DEADLINE)
    twice = await app.apply(once.content, [], deadline=DEADLINE)
    assert corpus.kept(twice.content) == corpus.kept(once.content)
    assert twice.inspection == once.inspection


def hostile() -> list[ParameterSet]:
    return [
        pytest.param(corpus, name, id=f"{app}-{name}", marks=pytest.mark.craft(app))
        for app, corpus in sorted(CORPORA.items())
        for name in corpus.hostile_names()
    ]


@pytest.mark.parametrize(("corpus", "name"), hostile())
async def test_a_hostile_file_ends_in_a_typed_failure_in_time(corpus: Corpus, name: str) -> None:
    with pytest.raises(AppFailed) as failed:
        await running(corpus).inspect(corpus.hostile_file(name), deadline=DEADLINE)
    assert failed.value.failure != "timeout", "refused, not left to run out its time"
