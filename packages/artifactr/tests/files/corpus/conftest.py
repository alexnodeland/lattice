"""The fidelity matrix: with `CRAFT_MATRIX` set, the live tests' results, a row a feature.

Each app's results are a table of their own, headed with its name, one column a check.
"""

import os
from collections import defaultdict
from pathlib import Path

import pytest

from artifactr.files.craft import CRAFTS
from tests.files.corpus.corpora import CORPORA

CHECKS = {
    "test_an_open_and_a_save_keep_the_feature": "Kept by an open and a save",
    "test_saving_twice_is_a_fixpoint": "Saving twice is a fixpoint",
}
_results: dict[str, dict[tuple[str, str], str]] = defaultdict(dict)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    name, _, case = report.nodeid.split("::")[-1].partition("[")
    if name not in CHECKS or (report.when != "call" and report.passed):
        return
    app, _, feature = case.rstrip("]").partition("-")
    if hasattr(report, "wasxfail"):
        outcome = "known" if report.skipped else "fixed"
    elif report.failed and report.when != "call":
        outcome = "error"  # the test couldn't run: not a feature lost
    else:
        outcome = report.outcome
    _results[app][name, feature] = outcome


def pytest_sessionfinish(session: pytest.Session) -> None:
    del session
    if not (path := os.environ.get("CRAFT_MATRIX")) or not _results:
        return
    mark = {
        "passed": "supported",
        "failed": "**not kept**",
        "known": "not supported",
        "fixed": "**supported, unlike before**",
        "error": "**could not run**",
        "skipped": "not run",
    }
    header = "| Feature | " + " | ".join(CHECKS.values()) + " |"
    rule = "|---" * (len(CHECKS) + 1) + "|"
    tables: list[str] = []
    for app, results in sorted(_results.items()):
        rows = [
            f"| {feature} | "
            + " | ".join(mark[results.get((n, feature), "skipped")] for n in CHECKS)
            + " |"
            for feature in sorted(CORPORA[app].makers)
        ]
        tables += [f"## {CRAFTS[app].title}'s fidelity", "", header, rule, *rows, ""]
    Path(path).write_text("\n".join(tables))
