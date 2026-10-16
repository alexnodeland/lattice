"""The release plan's invariants over every run it can be asked about (scripts/release_plan.py).

``test_release_plan.py`` has the plan's cases one by one. These enumerate a finite space of runs
that covers each thing the plan reads: for a push, every set of packages released, with every
tag right or one of them wrong in one way; for a dispatch, every tag it can name, every ref it
can run on and every mode; and the PyPI switch. Each run is planned against the repository's own
packages, and every outcome is held to what the script's docstring and ADR-0023 claim, as the
executable half of a specification.
"""

import functools
import itertools
from collections.abc import Iterator
from typing import Final

import pytest
import release_plan as rp

SHA: Final = "a" * 40
PACKAGES: Final = (*rp.WHEELS, rp.STACKR)
VERSIONS: Final = {path: str(rp.project(path)["version"]) for path in PACKAGES}
TAGS: Final = {path: f"{path.removeprefix('packages/')}-v{VERSIONS[path]}" for path in PACKAGES}
WRONG: Final = ("other commit", "malformed commit", "no commit", "no tag", "other version")
"""What can be wrong with one released package's tag."""

type Outcome = rp.Plan | rp.Refused


def outputs(path: str, wrong: str | None) -> dict[str, str]:
    """release-please's outputs for one released package, with ``wrong`` wrong with them."""
    tag, sha = f"{path}--tag_name", f"{path}--sha"
    found = {tag: TAGS[path], sha: SHA}
    match wrong:
        case "other commit":
            found[sha] = "b" * 40
        case "malformed commit":
            found[sha] = "abc"
        case "no commit":
            del found[sha]
        case "no tag":
            del found[tag]
        case "other version":
            found[tag] = f"{path.removeprefix('packages/')}-v9.9.9"
    return found


def pushes() -> Iterator[tuple[rp.Run, str | None, str | None]]:
    """Every release push, with the package whose tag is wrong and how, if one is."""
    for size in range(len(PACKAGES) + 1):
        for released, publishing in itertools.product(
            itertools.combinations(PACKAGES, size), (False, True)
        ):
            for deviant, wrong in [(None, None), *itertools.product(released, WRONG)]:
                releases: dict[str, str] = {}
                for path in released:
                    releases |= outputs(path, wrong if path == deviant else None)
                run = rp.Run(
                    event="push",
                    sha=SHA,
                    released=released,
                    releases=releases,
                    publishing=publishing,
                )
                yield run, deviant, wrong


def dispatches() -> Iterator[rp.Run]:
    """Every dispatch, naming any tag or none, on any ref, in any mode."""
    tags = [*TAGS.values(), "evalr-v9.9.9", "nope-v1"]
    for tag, ref_type, ref_name, mode, publishing in itertools.product(
        ["", *tags],
        ("branch", "tag"),
        ["main", *tags],
        ("rehearse", "publish", "ship"),
        (False, True),
    ):
        yield rp.Run(
            event="workflow_dispatch",
            sha=SHA,
            ref_type=ref_type,
            ref_name=ref_name,
            tag=tag,
            mode=mode,
            publishing=publishing,
        )


def outcome(run: rp.Run) -> Outcome:
    try:
        return rp.plan(run)
    except rp.Refused as refusal:
        return refusal


@pytest.fixture(scope="module")
def outcomes() -> Iterator[list[tuple[rp.Run, Outcome]]]:
    """Every run and its plan or refusal, with each pyproject read once."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rp, "project", functools.cache(rp.project))
        runs = [
            *(run for run, _, _ in pushes()),
            *dispatches(),
            rp.Run(event="pull_request", sha=SHA),
        ]
        yield [(run, outcome(run)) for run in runs]


def planned(outcomes: list[tuple[rp.Run, Outcome]]) -> Iterator[tuple[rp.Run, rp.Plan]]:
    return ((run, made) for run, made in outcomes if isinstance(made, rp.Plan))


def on_its_tag(run: rp.Run) -> bool:
    return run.event == "workflow_dispatch" and run.ref_type == "tag" and run.ref_name == run.tag


def test_the_space_is_planned_and_refused_alike(outcomes: list[tuple[rp.Run, Outcome]]) -> None:
    refused = sum(isinstance(made, rp.Refused) for _, made in outcomes)
    assert 0 < refused < len(outcomes)


def test_a_release_on_its_push_or_a_tag_dispatched_to_publish_writes_and_nothing_else(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    for run, made in planned(outcomes):
        writes = made.write and bool(made.packages or made.stackr)
        release = run.event == "push" and bool(run.released)
        assert writes == (release or (on_its_tag(run) and run.mode == "publish")), run
        if run.event == "workflow_dispatch":
            assert made.write == (run.mode == "publish"), run


def test_a_push_never_publishes_to_pypi(outcomes: list[tuple[rp.Run, Outcome]]) -> None:
    for run, made in planned(outcomes):
        if run.event == "push":
            assert not made.publish, run


def test_only_a_wheel_dispatched_on_its_tag_with_the_switch_on_is_published(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    published = [(run, made) for run, made in planned(outcomes) if made.publish]
    assert published
    for run, made in published:
        assert on_its_tag(run), run
        assert run.mode == "publish", run
        assert run.publishing, run
        assert made.packages == made.ordered == [rp.tag_path(run.tag)], run


def test_stackr_and_a_release_of_no_wheel_publish_nothing(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    for run, made in planned(outcomes):
        assert rp.STACKR not in made.packages, run
        if not made.packages:
            assert not made.publish, run
            assert made.ordered == [], run


def test_packages_are_published_after_what_they_require(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    # The requirements are read with the script's own readers, but not through STAGES.
    names = {rp.distribution(path): path for path in rp.WHEELS}
    requires = {
        path: {names[name] for name in rp.requirement_names(path) if name in names} - {path}
        for path in rp.WHEELS
    }
    assert any(requires.values()), "some package requires another, or this tests nothing"
    for run, made in planned(outcomes):
        assert sorted(made.ordered) == sorted(made.packages), run
        for position, path in enumerate(made.ordered):
            assert not requires[path] & set(made.ordered[position:]), (run, path)


def test_a_wheel_is_built_from_the_tag_of_its_pyprojects_version(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    for run, made in planned(outcomes):
        if run.event == "push" or run.tag:
            for path in made.packages:
                assert made.releases[f"{path}--tag_name"] == TAGS[path], run


def test_a_release_is_refused_unless_every_tag_is_whole_and_at_this_commit(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    pushed = [made for run, made in outcomes if run.event == "push"]
    for (run, deviant, wrong), made in zip(pushes(), pushed, strict=True):
        # stackr ships no wheel, and its images take the tag's version, whatever it is.
        tolerated = wrong is None or (deviant, wrong) == (rp.STACKR, "other version")
        assert isinstance(made, rp.Plan) == tolerated, (run, wrong, made)


def test_a_dispatch_runs_on_the_tag_it_names_in_a_mode_it_knows(
    outcomes: list[tuple[rp.Run, Outcome]],
) -> None:
    for run, made in outcomes:
        if run.event != "workflow_dispatch":
            continue
        known = run.mode in ("rehearse", "publish") and run.tag in ("", *TAGS.values())
        where = on_its_tag(run) if run.tag else run.mode == "rehearse"
        assert isinstance(made, rp.Plan) == (known and where), run
        if isinstance(made, rp.Plan) and not run.tag:
            assert made.packages == list(rp.WHEELS), run


def test_a_run_on_another_event_is_refused(outcomes: list[tuple[rp.Run, Outcome]]) -> None:
    [(_, made)] = [(run, made) for run, made in outcomes if run.event == "pull_request"]
    assert isinstance(made, rp.Refused)
