"""Plan a release's wheels: which packages, built from which commit, published in what order.

Usage: scripts/release_plan.py   (the workflow's environment names the run; see ``Run``)

``release.yml`` runs this first, in a job of its own, and every later job reads its outputs, so the
rules below are in one place and are tested (tests/test_release_plan.py):

- **A release is built from the commit it was tagged at, and attested as built there.**
  ``actions/attest`` records the workflow's own commit as the build provenance's source, so a
  release created on a later push than the one that merged its pull request would have wheels,
  from the tag's commit, whose provenance names another commit (#206). The run refuses, before
  building anything, and says how to run the workflow again on the tag, where the two are the
  same. The release then exists with no wheels until someone does.
- **A tag's version is its pyproject's.** The wheel carries the pyproject's, and PyPI keeps a
  version for ever.
- **Packages are published in dependency order,** in the stages ``STAGES`` names: a package after
  everything it requires, so that at every moment what is on PyPI installs. A test holds the
  stages to the packages' own requirements.
- **A rehearsal builds and checks everything and publishes nothing.** The workflow can be run by
  hand on a branch, to rehearse the whole release at its head; it can be run on a tag to build
  that release's wheels again, and to publish them if asked to.
"""

import json
import os
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parent.parent
STACKR: Final = "packages/stackr"
"""Ships no wheel: a release of it publishes the AWS recipe's thin images."""
STAGES: Final[tuple[tuple[str, ...], ...]] = (
    ("packages/lattice-core", "packages/evalr"),
    ("packages/artifactr", "packages/reflexr", "packages/grantr"),
    ("packages/relayr",),
    ("packages/portalr",),
)
"""The packages that ship a wheel, in the order they are published: each stage after the ones its
packages require, and within a stage in any order."""
WHEELS: Final = tuple(path for stage in STAGES for path in stage)
SHA: Final = re.compile(r"^[0-9a-f]{40}$")


class Refused(Exception):
    """A run that must not go on, with what to tell the operator."""


@dataclass(frozen=True)
class Run:
    """What the workflow's run is.

    Attributes:
        event: ``push`` (to main), or ``workflow_dispatch``.
        sha: The commit the workflow runs at, which an attestation names.
        ref_type: ``branch`` or ``tag``, of the ref a dispatch was run on.
        ref_name: That ref's name.
        tag: A dispatch's ``tag`` input: the release to build again; empty to rehearse.
        mode: A dispatch's ``mode`` input: ``rehearse`` or ``publish``.
        released: The packages release-please released on this push.
        releases: All of release-please's outputs, such as ``packages/x--sha``.
        publishing: Whether the repository has turned publishing to PyPI on (the
            ``PYPI_PUBLISH`` variable).
    """

    event: str
    sha: str
    ref_type: str = "branch"
    ref_name: str = "main"
    tag: str = ""
    mode: str = "rehearse"
    released: Sequence[str] = ()
    releases: Mapping[str, str] = field(default_factory=dict[str, str])
    publishing: bool = False


@dataclass(frozen=True)
class Plan:
    """What the later jobs do.

    Attributes:
        packages: The packages to build a wheel of, by directory.
        releases: Each one's ``<path>--tag_name`` and ``<path>--sha``, as release-please gives
            them, and stackr's, if its images are to be built.
        stackr: Whether stackr's thin images are built and published.
        upload: Whether the wheels are attached to their release.
        attest: Whether they are attested.
        publish: Whether they go to PyPI.
        stages: ``packages``, by publication stage; a stage may be empty.
        notes: What the run decided, in words.
    """

    packages: list[str]
    releases: dict[str, str]
    stackr: bool
    upload: bool
    attest: bool
    publish: bool
    stages: list[list[str]]
    notes: list[str]


def project(path: str, root: Path = ROOT) -> dict[str, Any]:
    """A package's ``[project]`` table."""
    return tomllib.loads((root / path / "pyproject.toml").read_text())["project"]


def requirement_names(path: str, root: Path = ROOT) -> set[str]:
    """The distributions a package requires, in its dependencies and its extras."""
    table = project(path, root)
    requirements: list[str] = list(table.get("dependencies", []))
    for found in table.get("optional-dependencies", {}).values():
        requirements.extend(found)
    return {
        re.split(r"[\s\[<>=!~;@(]", requirement, maxsplit=1)[0].lower().replace("_", "-")
        for requirement in requirements
    }


def stage_of(path: str) -> int:
    """The stage a package is published in."""
    return next(i for i, stage in enumerate(STAGES) if path in stage)


def check_stages(root: Path = ROOT) -> list[str]:
    """What is wrong with ``STAGES``: a package required by one published no later than it."""
    names = {path: str(project(path, root)["name"]).lower().replace("_", "-") for path in WHEELS}
    problems: list[str] = []
    for path in WHEELS:
        for required in requirement_names(path, root):
            earlier = next((other for other, name in names.items() if name == required), None)
            if earlier is not None and earlier != path and stage_of(earlier) >= stage_of(path):
                problems.append(f"{path} requires {required}, which is not published before it")
    return problems


def tag_path(tag: str, root: Path = ROOT) -> str:
    """The package a tag (``<package>-v<version>``) is a release of."""
    config = json.loads((root / "release-please-config.json").read_text())["packages"]
    for path, found in config.items():
        if re.fullmatch(rf"{re.escape(found['package-name'])}-v\d.*", tag):
            return str(path)
    raise Refused(f"{tag} is not the tag of a package's release")


def refuse_other_commit(run: Run, paths: Sequence[str]) -> None:
    """Refuse a release whose tagged commit is not the one this run is at (#206)."""
    other = {
        path: run.releases[f"{path}--sha"]
        for path in paths
        if run.releases[f"{path}--sha"] != run.sha
    }
    if not other:
        return
    again = "\n".join(
        f"  gh workflow run release.yml --ref {run.releases[f'{path}--tag_name']} "
        f"-f tag={run.releases[f'{path}--tag_name']} -f mode=publish"
        for path in other
    )
    tagged = ", ".join(
        f"{run.releases[f'{path}--tag_name']} at {sha[:12]}" for path, sha in other.items()
    )
    raise Refused(
        f"release-please tagged {tagged}, and this run is at {run.sha[:12]}. Wheels built here "
        f"would be attested as built at {run.sha[:12]}, not at the tag (#206), so none are built "
        "and nothing is published. The release exists with no wheels. Run the workflow again on "
        f"the tag, where the two are the same:\n{again}\n(drop `-f mode=publish` to rehearse "
        "first)"
    )


def refuse_wrong_version(paths: Sequence[str], releases: Mapping[str, str], root: Path) -> None:
    """Refuse a tag whose version is not the package's pyproject's at this commit."""
    for path in paths:
        tag = releases[f"{path}--tag_name"]
        version = str(project(path, root)["version"])
        if not tag.endswith(f"-v{version}"):
            raise Refused(f"{tag} is a release of {path}, whose pyproject.toml says {version}")


def plan(run: Run, root: Path = ROOT) -> Plan:
    """Plan a run, or refuse it.

    Raises:
        Refused: If the run must not go on.
    """
    problems = check_stages(root)
    if problems:
        raise Refused("release_plan.STAGES is out of order: " + "; ".join(problems))
    if run.event == "push":
        released = list(run.released)
        for path in released:
            if not SHA.fullmatch(run.releases.get(f"{path}--sha", "")):
                raise Refused(f"release-please gave {path} no commit: {released}")
        refuse_other_commit(run, released)
        packages = [path for path in WHEELS if path in released]
        refuse_wrong_version(packages, run.releases, root)
        return built(
            run,
            packages,
            run.releases,
            STACKR in released,
            False,
            run.publishing,
            ["a release: its wheels are attached, attested and, if publishing is on, published"],
        )
    if run.event != "workflow_dispatch":
        raise Refused(f"the workflow doesn't run on {run.event}")
    if run.mode not in {"rehearse", "publish"}:
        raise Refused(f"mode is rehearse or publish, not {run.mode!r}")
    if not run.tag:
        if run.mode == "publish":
            raise Refused("only a release is published: name its tag, and run on the tag")
        return built(
            run,
            list(WHEELS),
            {
                f"{path}--{field}": value
                for path in WHEELS
                for field, value in (("tag_name", "rehearsal"), ("sha", run.sha))
            },
            False,
            True,
            False,
            [
                f"a rehearsal at {run.sha[:12]}: every wheel is built and checked, and nothing is "
                "attached, attested or published"
            ],
        )
    if run.ref_type != "tag" or run.ref_name != run.tag:
        raise Refused(f"run the workflow on the tag, not on {run.ref_name}: --ref {run.tag}")
    path = tag_path(run.tag, root)
    releases = {f"{path}--tag_name": run.tag, f"{path}--sha": run.sha}
    packages = [] if path == STACKR else [path]
    refuse_wrong_version(packages, releases, root)
    if run.mode == "publish" and not run.publishing:
        raise Refused("mode=publish needs the PYPI_PUBLISH repository variable set to true")
    return built(
        run,
        packages,
        releases,
        path == STACKR,
        False,
        run.mode == "publish",
        [
            f"{run.tag} again, from its own commit: its wheels are replaced on the release, "
            "attested and, in mode publish, published"
        ],
    )


def built(
    run: Run,
    packages: list[str],
    releases: Mapping[str, str],
    stackr: bool,
    rehearsal: bool,
    publish: bool,
    notes: list[str],
) -> Plan:
    """The plan for these packages."""
    wheels = set(packages)
    stages = [[path for path in stage if path in wheels] for stage in STAGES]
    released = [*packages, *([STACKR] if stackr else [])]
    keys = [f"{path}--{field}" for path in released for field in ("tag_name", "sha")]
    if stackr and run.event != "push":
        releases = {**releases, f"{STACKR}--tag_name": run.tag, f"{STACKR}--sha": run.sha}
    return Plan(
        packages=packages,
        releases={key: releases[key] for key in keys},
        stackr=stackr,
        upload=not rehearsal,
        attest=not rehearsal,
        publish=publish and not rehearsal,
        stages=stages,
        notes=notes,
    )


def entry(path: str) -> dict[str, str]:
    """A package as a job matrix names it: its directory, and a name for its artifacts."""
    return {"path": path, "slug": path.rsplit("/", 1)[-1]}


def outputs(made: Plan) -> dict[str, str]:
    """The plan as the workflow's job outputs."""
    flags = {
        "stackr": made.stackr,
        "upload": made.upload,
        "attest": made.attest,
        "publish": made.publish,
    }
    return {
        "packages": json.dumps([entry(path) for path in made.packages]),
        "releases": json.dumps(made.releases),
        **{name: str(value).lower() for name, value in flags.items()},
        **{
            f"stage{i}": json.dumps([entry(path) for path in stage])
            for i, stage in enumerate(made.stages, 1)
        },
    }


def environment(env: Mapping[str, str]) -> Run:
    """The run the workflow's environment describes."""
    return Run(
        event=env["EVENT"],
        sha=env["SHA"],
        ref_type=env.get("REF_TYPE", "branch"),
        ref_name=env.get("REF_NAME", "main"),
        tag=env.get("INPUT_TAG", ""),
        mode=env.get("INPUT_MODE") or "rehearse",
        released=json.loads(env.get("PATHS_RELEASED") or "[]"),
        releases=json.loads(env.get("RELEASES") or "{}"),
        publishing=env.get("PYPI_PUBLISH") == "true",
    )


def main() -> int:
    """Plan the run in the environment, write the outputs, and say what was decided."""
    try:
        made = plan(environment(os.environ))
    except Refused as refusal:
        sys.stderr.write(f"release_plan: {refusal}\n")
        return 1
    lines = "".join(f"{name}={value}\n" for name, value in outputs(made).items())
    if target := os.environ.get("GITHUB_OUTPUT"):
        with Path(target).open("a") as handle:
            handle.write(lines)
    else:
        sys.stdout.write(lines)
    sys.stderr.write("".join(f"release_plan: {note}\n" for note in made.notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
