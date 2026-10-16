"""The release workflow's plan (scripts/release_plan.py): what it builds and publishes, and what
it refuses."""

import json
from pathlib import Path

import pytest
import release_plan as rp
import yaml

SHA = "a" * 40
LATER = "b" * 40


def releases(*paths: str, sha: str = SHA, version: str = "0.1.0") -> dict[str, str]:
    """release-please's outputs for packages it released, as of one commit."""
    names = {p: p.removeprefix("packages/") for p in paths}
    out = {f"{p}--tag_name": f"{n}-v{version}" for p, n in names.items()}
    return out | {f"{p}--sha": sha for p in paths}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A repository in which every package says version 0.1.0, and release-please knows them."""
    for each in rp.WHEELS:
        folder = tmp_path / each
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "pyproject.toml").write_text(
            f'[project]\nname = "{each.rsplit("/", 1)[-1]}-ai"\nversion = "0.1.0"\n'
        )
    config = {
        "packages": {
            each: {"package-name": each.rsplit("/", 1)[-1]} for each in [*rp.WHEELS, rp.STACKR]
        }
    }
    (tmp_path / "release-please-config.json").write_text(json.dumps(config))
    return tmp_path


def push(*paths: str, sha: str = SHA, publishing: bool = False) -> rp.Run:
    return rp.Run(
        event="push",
        sha=sha,
        released=paths,
        releases=releases(*paths),
        publishing=publishing,
    )


def on_tag(tag: str, mode: str = "rehearse", *, publishing: bool = False) -> rp.Run:
    return rp.Run(
        event="workflow_dispatch",
        sha=SHA,
        ref_type="tag",
        ref_name=tag,
        tag=tag,
        mode=mode,
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


def test_a_stage_out_of_order_is_found(root: Path) -> None:
    (root / "packages/lattice-core/pyproject.toml").write_text(
        '[project]\nname = "lattice-core"\nversion = "0.1.0"\ndependencies = ["portalr-ai>=0.1"]\n'
    )
    assert rp.check_stages(root) == [
        "packages/lattice-core requires portalr-ai, which is not published before it"
    ]


def test_a_release_on_its_own_push_is_built_attested_and_ordered(root: Path) -> None:
    made = rp.plan(
        push("packages/portalr", "packages/lattice-core", "packages/stackr", publishing=True), root
    )
    assert made.packages == ["packages/lattice-core", "packages/portalr"]
    assert made.stackr
    assert (made.write, made.publish) == (True, True)
    assert made.ordered == ["packages/lattice-core", "packages/portalr"]
    assert set(made.releases) == {
        f"{path}--{field}"
        for path in ("packages/lattice-core", "packages/portalr", "packages/stackr")
        for field in ("tag_name", "sha")
    }, "only the keys the jobs read: release-please's notes stay out of the outputs"


def test_publishing_is_off_until_the_repository_turns_it_on(root: Path) -> None:
    made = rp.plan(push("packages/evalr"), root)
    assert (made.write, made.publish) == (True, False)


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
    assert "attaches and attests the wheels" in text
    assert "only if the PYPI_PUBLISH variable is true" in text
    assert "none is built" in text
    assert "pushes them" not in text, "a wheel's recovery doesn't talk of images"


def test_stackrs_release_at_another_commit_says_how_its_images_are_pushed(root: Path) -> None:
    run = rp.Run(
        event="push",
        sha=LATER,
        released=["packages/stackr"],
        releases=releases("packages/stackr"),
    )
    with pytest.raises(rp.Refused) as refusal:
        rp.plan(run, root)
    text = str(refusal.value)
    assert "stackr-v0.1.0 at aaaaaaaaaaaa" in text
    assert "-f tag=stackr-v0.1.0 -f mode=publish" in text
    assert "builds the images again, pushes them and adds them to the release's notes" in text
    assert "never on PyPI" in text
    assert "PYPI_PUBLISH" not in text, "stackr has no wheel: the switch is not its concern"


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
    with pytest.raises(rp.Refused, match=r"evalr-v0\.2\.0 .* whose pyproject.toml says 0\.1\.0"):
        rp.plan(run, root)


def test_a_push_that_releases_nothing_builds_nothing(root: Path) -> None:
    made = rp.plan(push(), root)
    assert made.packages == []
    assert not made.stackr
    assert made.ordered == []


def test_a_rehearsal_on_a_branch_builds_every_wheel_and_writes_nothing(root: Path) -> None:
    made = rp.plan(rp.Run(event="workflow_dispatch", sha=SHA, publishing=True), root)
    assert made.packages == list(rp.WHEELS)
    assert (made.write, made.publish, made.stackr) == (False, False, False)
    assert made.releases["packages/portalr--tag_name"] == "rehearsal"
    assert made.releases["packages/portalr--sha"] == SHA


def test_only_a_release_is_published_by_hand(root: Path) -> None:
    run = rp.Run(event="workflow_dispatch", sha=SHA, mode="publish", publishing=True)
    with pytest.raises(rp.Refused, match="only a release is published"):
        rp.plan(run, root)


def test_a_rehearsal_on_a_tag_builds_that_release_and_writes_nothing(root: Path) -> None:
    made = rp.plan(on_tag("evalr-v0.1.0", publishing=True), root)
    assert made.packages == ["packages/evalr"]
    assert made.releases == {"packages/evalr--tag_name": "evalr-v0.1.0", "packages/evalr--sha": SHA}
    assert (made.write, made.publish) == (False, False)


def test_publishing_a_tag_attaches_and_attests_whatever_the_pypi_switch(root: Path) -> None:
    without = rp.plan(on_tag("evalr-v0.1.0", "publish"), root)
    assert (without.write, without.publish) == (True, False)
    with_switch = rp.plan(on_tag("evalr-v0.1.0", "publish", publishing=True), root)
    assert (with_switch.write, with_switch.publish) == (True, True)


def test_stackrs_tag_rehearses_its_images_without_pushing_and_publishes_them_on_request(
    root: Path,
) -> None:
    rehearsal = rp.plan(on_tag("stackr-v0.1.0", publishing=True), root)
    assert rehearsal.packages == []
    assert rehearsal.stackr
    assert (rehearsal.write, rehearsal.publish) == (False, False), "builds the archives only"
    assert rehearsal.releases == {
        "packages/stackr--tag_name": "stackr-v0.1.0",
        "packages/stackr--sha": SHA,
    }
    published = rp.plan(on_tag("stackr-v0.1.0", "publish"), root)
    assert published.stackr
    assert (published.write, published.publish) == (True, False), "images, and never PyPI"


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
    ],
)
def test_a_run_that_must_not_go_on_is_refused(root: Path, run: rp.Run, message: str) -> None:
    with pytest.raises(rp.Refused, match=message):
        rp.plan(run, root)


def test_the_outputs_are_what_the_workflow_reads(root: Path) -> None:
    out = rp.outputs(
        rp.plan(
            push("packages/relayr", "packages/artifactr", "packages/reflexr", publishing=True), root
        ),
        root,
    )
    ordered = json.loads(out["ordered"])
    assert [each["path"] for each in ordered] == [
        "packages/artifactr",
        "packages/reflexr",
        "packages/relayr",
    ]
    assert ordered[0]["earlier"] == []
    assert ordered[2]["earlier"] == ["artifactr-ai==0.1.0", "reflexr-ai==0.1.0"]
    assert {each["slug"] for each in json.loads(out["packages"])} == {
        "artifactr",
        "reflexr",
        "relayr",
    }
    assert (out["publish"], out["write"], out["stackr"]) == ("true", "true", "false")


def test_the_environment_describes_the_run() -> None:
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


WORKFLOW = yaml.safe_load(
    (Path(__file__).parent.parent / ".github/workflows/release.yml").read_text()
)
JOBS = WORKFLOW["jobs"]
WRITERS = {"attach", "publish-images", "release-notes", "release-please", "pypi-publish"}
"""The jobs that may write, or publish, and so run only where the plan says to."""


def test_only_the_jobs_that_write_have_write_permissions() -> None:
    def writes(job: dict[str, object]) -> bool:
        permissions = job.get("permissions") or {}
        assert isinstance(permissions, dict)
        return any(level == "write" for level in permissions.values()) or "environment" in job

    assert {name for name, job in JOBS.items() if writes(job)} == WRITERS - {"release-please"}, (
        "a rehearsal reaches the build and check jobs and none of these"
    )


@pytest.mark.parametrize("name", ["attach", "publish-images", "release-notes", "pypi-publish"])
def test_a_writing_job_runs_only_where_the_plan_writes(name: str) -> None:
    condition = str(JOBS[name]["if"])
    assert (
        "needs.plan.outputs.write == 'true'" in condition
        or "outputs.publish == 'true'" in condition
    )


def test_pypi_publishes_one_package_at_a_time_and_stops_at_the_first_failure() -> None:
    job = JOBS["pypi-publish"]
    assert job["strategy"]["max-parallel"] == 1
    assert job["strategy"]["fail-fast"] is True
    assert job["environment"] == "pypi"
    assert "needs.plan.outputs.ordered" in job["strategy"]["matrix"]["package"]
    assert "needs.plan.outputs.publish == 'true'" in job["if"]


def test_the_build_job_is_read_only() -> None:
    assert JOBS["build"]["permissions"] == {"contents": "read"}
