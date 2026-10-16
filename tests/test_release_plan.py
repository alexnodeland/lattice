"""The release workflow's plan (scripts/release_plan.py): what it builds and publishes, and what
it refuses."""

import json
from pathlib import Path

import pytest
import release_plan as rp

SHA = "a" * 40
LATER = "b" * 40


def releases(*paths: str, sha: str = SHA, version: str = "0.1.0") -> dict[str, str]:
    """release-please's outputs for packages it released, as of one commit."""
    names = {p: p.removeprefix("packages/") for p in paths}
    out = {f"{p}--tag_name": f"{n}-v{version}" for p, n in names.items()}
    return out | {f"{p}--sha": sha for p in paths}


def published(path: str, version: str, tmp: Path) -> Path:
    """A repository root in which this package's pyproject says this version."""
    for each in rp.WHEELS:
        folder = tmp / each
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "pyproject.toml").write_text(
            f'[project]\nname = "{each.rsplit("/", 1)[-1]}"\nversion = "{version}"\n'
        )
    (tmp / "release-please-config.json").write_text(
        json.dumps(
            {
                "packages": {
                    each: {"package-name": each.rsplit("/", 1)[-1]}
                    for each in [*rp.WHEELS, rp.STACKR]
                }
            }
        )
    )
    return tmp


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return published("", "0.1.0", tmp_path)


def push(*paths: str, sha: str = SHA, publishing: bool = False, **more: str) -> rp.Run:
    return rp.Run(
        event="push",
        sha=sha,
        released=paths,
        releases=releases(*paths) | more,
        publishing=publishing,
    )


def test_the_stages_follow_the_packages_own_requirements() -> None:
    assert rp.check_stages() == []
    assert set(rp.WHEELS) == {
        "packages/lattice-core",
        "packages/evalr",
        "packages/artifactr",
        "packages/reflexr",
        "packages/grantr",
        "packages/relayr",
        "packages/portalr",
    }, "every package that ships a wheel is in a stage, and stackr is not"


def test_a_stage_out_of_order_is_found(tmp_path: Path) -> None:
    root = published("", "0.1.0", tmp_path)
    (root / "packages/lattice-core/pyproject.toml").write_text(
        '[project]\nname = "lattice-core"\nversion = "0.1.0"\ndependencies = ["portalr>=0.1"]\n'
    )
    assert rp.check_stages(root) == [
        "packages/lattice-core requires portalr, which is not published before it"
    ]


def test_a_release_on_its_own_push_is_built_attested_and_ordered(root: Path) -> None:
    made = rp.plan(
        push("packages/portalr", "packages/lattice-core", "packages/stackr", publishing=True), root
    )
    assert made.packages == ["packages/lattice-core", "packages/portalr"]
    assert made.stackr
    assert (made.upload, made.attest, made.publish) == (True, True, True)
    assert made.stages == [["packages/lattice-core"], [], [], ["packages/portalr"]]
    assert set(made.releases) == {
        f"{path}--{field}"
        for path in ("packages/lattice-core", "packages/portalr", "packages/stackr")
        for field in ("tag_name", "sha")
    }, "only the keys the jobs read: release-please's notes stay out of the outputs"


def test_publishing_is_off_until_the_repository_turns_it_on(root: Path) -> None:
    assert not rp.plan(push("packages/evalr"), root).publish


def test_a_release_whose_tag_is_another_commit_is_refused_with_how_to_run_it_on_the_tag(
    root: Path,
) -> None:
    run = rp.Run(
        event="push",
        sha=LATER,
        released=["packages/evalr"],
        releases=releases("packages/evalr"),
    )
    with pytest.raises(rp.Refused) as refusal:
        rp.plan(run, root)
    text = str(refusal.value)
    assert "evalr-v0.1.0 at aaaaaaaaaaaa" in text
    assert "this run is at bbbbbbbbbbbb" in text
    assert (
        "gh workflow run release.yml --ref evalr-v0.1.0 -f tag=evalr-v0.1.0 -f mode=publish" in text
    )
    assert "none are built" in text


def test_stackrs_release_is_held_to_the_same_commit_since_its_images_are_attested(
    root: Path,
) -> None:
    run = rp.Run(
        event="push",
        sha=LATER,
        released=["packages/stackr"],
        releases=releases("packages/stackr"),
    )
    with pytest.raises(rp.Refused, match=r"stackr-v0\.1\.0 at aaaaaaaaaaaa"):
        rp.plan(run, root)


@pytest.mark.parametrize("sha", ["", "abc", "A" * 40, "g" * 40])
def test_a_released_package_without_a_full_commit_is_refused(root: Path, sha: str) -> None:
    run = rp.Run(
        event="push",
        sha=SHA,
        released=["packages/evalr"],
        releases={"packages/evalr--tag_name": "evalr-v0.1.0", "packages/evalr--sha": sha},
    )
    with pytest.raises(rp.Refused, match="gave packages/evalr no commit"):
        rp.plan(run, root)


def test_a_released_package_with_no_sha_at_all_is_refused(root: Path) -> None:
    run = rp.Run(event="push", sha=SHA, released=["packages/evalr"], releases={})
    with pytest.raises(rp.Refused, match="no commit"):
        rp.plan(run, root)


def test_a_tag_whose_version_is_not_the_pyprojects_is_refused(root: Path) -> None:
    run = rp.Run(
        event="push",
        sha=SHA,
        released=["packages/evalr"],
        releases=releases("packages/evalr", version="0.2.0"),
    )
    with pytest.raises(
        rp.Refused,
        match=r"evalr-v0.2.0 is a release of packages/evalr, whose pyproject.toml says 0.1.0",
    ):
        rp.plan(run, root)


def test_a_push_that_releases_nothing_builds_nothing(root: Path) -> None:
    made = rp.plan(push(), root)
    assert made.packages == []
    assert not made.stackr
    assert made.stages == [[], [], [], []]


def test_a_rehearsal_on_a_branch_builds_every_wheel_and_does_nothing_more(root: Path) -> None:
    run = rp.Run(event="workflow_dispatch", sha=SHA, publishing=True)
    made = rp.plan(run, root)
    assert made.packages == list(rp.WHEELS)
    assert (made.upload, made.attest, made.publish, made.stackr) == (False,) * 4
    assert made.releases["packages/portalr--tag_name"] == "rehearsal"
    assert made.releases["packages/portalr--sha"] == SHA


def test_only_a_release_is_published_by_hand(root: Path) -> None:
    run = rp.Run(event="workflow_dispatch", sha=SHA, mode="publish", publishing=True)
    with pytest.raises(rp.Refused, match="only a release is published"):
        rp.plan(run, root)


def test_a_release_run_again_on_its_tag_is_built_from_the_tag(root: Path) -> None:
    run = rp.Run(
        event="workflow_dispatch",
        sha=SHA,
        ref_type="tag",
        ref_name="evalr-v0.1.0",
        tag="evalr-v0.1.0",
        mode="publish",
        publishing=True,
    )
    made = rp.plan(run, root)
    assert made.packages == ["packages/evalr"]
    assert made.releases == {"packages/evalr--tag_name": "evalr-v0.1.0", "packages/evalr--sha": SHA}
    assert (made.upload, made.attest, made.publish) == (True, True, True)


def test_a_release_run_again_on_its_tag_rehearses_by_default(root: Path) -> None:
    run = rp.Run(
        event="workflow_dispatch",
        sha=SHA,
        ref_type="tag",
        ref_name="evalr-v0.1.0",
        tag="evalr-v0.1.0",
    )
    assert not rp.plan(run, root).publish


def test_stackrs_tag_run_again_builds_its_images_and_no_wheel(root: Path) -> None:
    run = rp.Run(
        event="workflow_dispatch",
        sha=SHA,
        ref_type="tag",
        ref_name="stackr-v0.1.0",
        tag="stackr-v0.1.0",
    )
    made = rp.plan(run, root)
    assert made.packages == []
    assert made.stackr
    assert made.releases == {
        "packages/stackr--tag_name": "stackr-v0.1.0",
        "packages/stackr--sha": SHA,
    }


@pytest.mark.parametrize(
    ("run", "message"),
    [
        (
            rp.Run(event="workflow_dispatch", sha=SHA, tag="evalr-v0.1.0"),
            "run the workflow on the tag",
        ),
        (
            rp.Run(
                event="workflow_dispatch",
                sha=SHA,
                ref_type="tag",
                ref_name="x-v1",
                tag="evalr-v0.1.0",
            ),
            "run the workflow on the tag",
        ),
        (
            rp.Run(
                event="workflow_dispatch",
                sha=SHA,
                ref_type="tag",
                ref_name="nope-v1",
                tag="nope-v1",
            ),
            "not the tag of a package",
        ),
        (rp.Run(event="workflow_dispatch", sha=SHA, mode="ship"), "mode is rehearse or publish"),
        (rp.Run(event="pull_request", sha=SHA), "doesn't run on pull_request"),
        (
            rp.Run(
                event="workflow_dispatch",
                sha=SHA,
                ref_type="tag",
                ref_name="evalr-v0.1.0",
                tag="evalr-v0.1.0",
                mode="publish",
            ),
            "needs the PYPI_PUBLISH repository variable",
        ),
    ],
)
def test_a_run_that_must_not_go_on_is_refused(root: Path, run: rp.Run, message: str) -> None:
    with pytest.raises(rp.Refused, match=message):
        rp.plan(run, root)


def test_the_outputs_are_what_the_workflow_reads(root: Path) -> None:
    out = rp.outputs(rp.plan(push("packages/artifactr", "packages/reflexr", publishing=True), root))
    assert json.loads(out["stage2"]) == [
        {"path": "packages/artifactr", "slug": "artifactr"},
        {"path": "packages/reflexr", "slug": "reflexr"},
    ]
    assert [each["path"] for each in json.loads(out["packages"])] == [
        "packages/artifactr",
        "packages/reflexr",
    ]
    assert json.loads(out["stage1"]) == []
    assert json.loads(out["stage4"]) == []
    assert (out["publish"], out["stackr"], out["upload"]) == ("true", "false", "true")


def test_the_environment_describes_the_run(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    env = {
        "EVENT": "push",
        "SHA": SHA,
        "PATHS_RELEASED": json.dumps(["packages/evalr"]),
        "RELEASES": json.dumps(releases("packages/evalr")),
        "PYPI_PUBLISH": "true",
    }
    run = rp.environment(env)
    assert run.event == "push"
    assert run.publishing
    assert run.released == ["packages/evalr"]
    assert (
        rp.environment({"EVENT": "workflow_dispatch", "SHA": SHA, "INPUT_MODE": ""}).mode
        == "rehearse"
    )


def test_main_writes_the_outputs_and_refuses_with_a_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "output"
    monkeypatch.setattr(rp, "ROOT", Path(__file__).parent.parent)
    monkeypatch.setenv("GITHUB_OUTPUT", str(target))
    monkeypatch.setenv("EVENT", "workflow_dispatch")
    monkeypatch.setenv("SHA", SHA)
    assert rp.main() == 0
    assert "packages=" in target.read_text()
    assert "rehearsal" in capsys.readouterr().err
    monkeypatch.setenv("EVENT", "pull_request")
    monkeypatch.delenv("GITHUB_OUTPUT")
    assert rp.main() == 1
    assert "doesn't run on pull_request" in capsys.readouterr().err
