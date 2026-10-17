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
- **A rehearsal writes nothing.** Run by hand, the workflow's ``mode`` is ``rehearse`` unless it
  says ``publish``: it builds and checks, and attaches nothing to a release, attests nothing,
  pushes no image, rewrites no release notes and publishes nothing, on a branch (the whole release
  at its head) and on a tag alike. Attaching, attesting and pushing images happen in a release
  run, or in ``mode=publish`` on a tag. **Publishing to PyPI happens only in ``mode=publish`` on
  a tag, one package a dispatch**: a release run never publishes. It lists the dispatches to run.
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
            them, and stackr's, if its images are built.
        stackr: Whether stackr's thin images are built.
        write: Whether the run writes anywhere: wheels attached to their release and attested,
            images pushed and added to the release's notes. A rehearsal never does.
        publish: Whether the wheels go to PyPI.
        ordered: ``packages``, in the order they are published (``STAGES``).
        notes: What the run decided, in words.
    """

    packages: list[str]
    releases: dict[str, str]
    stackr: bool
    write: bool
    publish: bool
    ordered: list[str]
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


def again(tag: str, path: str) -> str:
    """How to run the workflow again on a tag, and what that does."""
    command = f"gh workflow run release.yml --ref {tag} -f tag={tag} -f mode=publish"
    if path == STACKR:
        return (
            f"  {command}\n    (it builds the images again, pushes them and adds them to the "
            "release's notes; stackr has no wheel and is never on PyPI)"
        )
    return (
        f"  {command}\n    (it attaches and attests the wheels; it publishes to PyPI as well "
        "only if the PYPI_PUBLISH variable is true, and then after the approval of the "
        "package's `pypi-<distribution>` environment)"
    )


def refuse_other_commit(run: Run, paths: Sequence[str]) -> None:
    """Refuse a release whose tagged commit is not the one this run is at (#206)."""
    other = {
        path: run.releases[f"{path}--sha"]
        for path in paths
        if run.releases[f"{path}--sha"] != run.sha
    }
    if not other:
        return
    commands = "\n".join(again(run.releases[f"{path}--tag_name"], path) for path in other)
    tagged = ", ".join(
        f"{run.releases[f'{path}--tag_name']} at {sha[:12]}" for path, sha in other.items()
    )
    raise Refused(
        f"release-please tagged {tagged}, and this run is at {run.sha[:12]}. What is built here "
        f"would be attested as built at {run.sha[:12]}, not at the tag (#206), so none is built "
        "and nothing is published. The release exists with no wheels. Run the workflow again on "
        f"the tag, where the two are the same:\n{commands}\nTo build and check it first, "
        "without writing anything, drop `-f mode=publish`."
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
            if not run.releases.get(f"{path}--tag_name"):
                raise Refused(f"release-please gave {path} no tag: {released}")
        refuse_other_commit(run, released)
        packages = [path for path in WHEELS if path in released]
        refuse_wrong_version(packages, run.releases, root)
        return built(
            run,
            packages,
            run.releases,
            STACKR in released,
            True,
            False,
            ["a release: its wheels are attached and attested; PyPI is by dispatch on each tag"],
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
            False,
            False,
            [
                f"a rehearsal at {run.sha[:12]}: every wheel is built and checked, and nothing is "
                "attached, attested, pushed or published"
            ],
        )
    if run.ref_type != "tag" or run.ref_name != run.tag:
        raise Refused(f"run the workflow on the tag, not on {run.ref_name}: --ref {run.tag}")
    path = tag_path(run.tag, root)
    releases = {f"{path}--tag_name": run.tag, f"{path}--sha": run.sha}
    packages = [] if path == STACKR else [path]
    refuse_wrong_version(packages, releases, root)
    writes = run.mode == "publish"
    if not writes:
        note = f"{run.tag} rebuilt and checked, writing nothing (mode rehearse)"
    elif path == STACKR:
        note = f"{run.tag} again: its images are built, pushed and added to the release's notes"
    else:
        note = f"{run.tag} again: its wheels replace the release's, and go to PyPI if that is on"
    return built(
        run,
        packages,
        releases,
        path == STACKR,
        writes,
        writes and run.publishing and bool(packages),
        [note],
    )


def built(
    run: Run,
    packages: list[str],
    releases: Mapping[str, str],
    stackr: bool,
    write: bool,
    publish: bool,
    notes: list[str],
) -> Plan:
    """The plan for these packages."""
    wheels = set(packages)
    ordered = [path for stage in STAGES for path in stage if path in wheels]
    released = [*packages, *([STACKR] if stackr else [])]
    keys = [f"{path}--{field}" for path in released for field in ("tag_name", "sha")]
    if stackr and run.event != "push":
        releases = {**releases, f"{STACKR}--tag_name": run.tag, f"{STACKR}--sha": run.sha}
    return Plan(
        packages=packages,
        releases={key: releases[key] for key in keys},
        stackr=stackr,
        write=write,
        publish=publish and write,
        ordered=ordered,
        notes=notes,
    )


def distribution(path: str, root: Path = ROOT) -> str:
    """A package's distribution, as PyPI names it."""
    return str(project(path, root)["name"]).lower().replace("_", "-")


def requires(path: str, root: Path = ROOT) -> list[str]:
    """The ``name==version`` of every other package of the repository that a package requires.

    PyPI must serve these before the package is published, whether or not they are in this
    release: a dispatch on one tag publishes one package, and its requirements were published by
    the dispatches before it. The version is the one the repository's package has at this commit.
    """
    names = {distribution(other, root): other for other in WHEELS}
    found = requirement_names(path, root) & names.keys() - {distribution(path, root)}
    return [f"{name}=={project(names[name], root)['version']}" for name in sorted(found)]


def entry(path: str, root: Path = ROOT) -> dict[str, Any]:
    """A package as a job matrix names it.

    Its directory, a name for artifacts, its stage, its distribution and version, and what PyPI
    must serve before it.
    """
    return {
        "path": path,
        "slug": path.rsplit("/", 1)[-1],
        "stage": stage_of(path) + 1,
        "name": distribution(path, root),
        "version": str(project(path, root)["version"]),
        "requires": requires(path, root),
    }


def outputs(made: Plan, root: Path = ROOT) -> dict[str, str]:
    """The plan as the workflow's job outputs.

    ``ordered`` is what the publishing job runs through, in the order the packages are published.
    """
    flags = {"stackr": made.stackr, "write": made.write, "publish": made.publish}
    return {
        "packages": json.dumps([entry(path, root) for path in made.packages]),
        "ordered": json.dumps([entry(path, root) for path in made.ordered]),
        "releases": json.dumps(made.releases),
        **{name: str(value).lower() for name, value in flags.items()},
    }


def next_steps(made: Plan, run: Run) -> list[str]:
    """What the owner runs after a release run, in order.

    One dispatch for each package to publish; for stackr, nothing (its images were pushed).
    """
    if run.event != "push":
        return []
    return [
        f"gh workflow run release.yml --ref {made.releases[f'{path}--tag_name']} "
        f"-f tag={made.releases[f'{path}--tag_name']} -f mode=publish"
        for path in made.ordered
    ]


def environment(env: Mapping[str, str]) -> Run:
    """The run the workflow's environment describes."""
    return Run(
        event=env["EVENT"],
        sha=env["SHA"],
        ref_type=env.get("REF_TYPE", "branch"),
        ref_name=env.get("REF_NAME", "main"),
        tag=env.get("INPUT_TAG", ""),
        mode=env.get("INPUT_MODE") or "rehearse",  # a push has no inputs: it is a release run
        released=json.loads(env.get("PATHS_RELEASED") or "[]"),
        releases=json.loads(env.get("RELEASES") or "{}"),
        publishing=env.get("PYPI_PUBLISH") == "true",
    )


def main() -> int:
    """Plan the run in the environment, write the outputs, and say what was decided."""
    try:
        run = environment(os.environ)
        made = plan(run)
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
    steps = next_steps(made, run)
    if steps and (summary := os.environ.get("GITHUB_STEP_SUMMARY")):
        with Path(summary).open("a") as handle:
            handle.write(
                "### Publish to PyPI\n\nThis run attached and attested the wheels. It published "
                "nothing. Publish each package by dispatch on its tag, in this order, approving "
                "each package's `pypi-<distribution>` environment (one approval a package, one "
                "at a time):\n\n" + "".join(f"1. `{step}`\n" for step in steps)
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
