"""The fidelity matrix: with `WORDCRAFT_MATRIX` set, the live tests' results, one row a feature."""

import os
from pathlib import Path

import pytest

from tests.files.corpus.make import FEATURES

CHECKS = {
    "test_an_open_and_a_save_keep_the_feature": "Kept by an open and a save",
    "test_saving_twice_is_a_fixpoint": "Saving twice is a fixpoint",
}
_results: dict[tuple[str, str], str] = {}


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    name, _, feature = report.nodeid.split("::")[-1].partition("[")
    if name not in CHECKS or (report.when != "call" and report.passed):
        return
    if hasattr(report, "wasxfail"):
        outcome = "known" if report.skipped else "fixed"
    elif report.failed and report.when != "call":
        outcome = "error"  # the test couldn't run: not a feature lost
    else:
        outcome = report.outcome
    _results[name, feature.rstrip("]")] = outcome


def pytest_sessionfinish(session: pytest.Session) -> None:
    del session
    if not (path := os.environ.get("WORDCRAFT_MATRIX")) or not _results:
        return
    mark = {
        "passed": "supported",
        "failed": "**not kept**",
        "known": "not supported",
        "fixed": "**supported, unlike before**",
        "error": "**could not run**",
        "skipped": "not run",
    }
    rows = [
        f"| {feature} | "
        + " | ".join(mark[_results.get((n, feature), "skipped")] for n in CHECKS)
        + " |"
        for feature in sorted(FEATURES)
    ]
    header = "| Feature | " + " | ".join(CHECKS.values()) + " |"
    rule = "|---" * (len(CHECKS) + 1) + "|"
    Path(path).write_text("\n".join(["## WordCraft's fidelity", "", header, rule, *rows, ""]))
