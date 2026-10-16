"""What PyPI serves of the files a release publishes, read from its simple index.

Usage:
  scripts/pypi.py report DIR            what PyPI has of each file in DIR, by name and hash
  scripts/pypi.py wait DIR              wait until PyPI serves every file in DIR, with its hash
  scripts/pypi.py require NAME==VERSION...   fail unless PyPI serves each (the packages a
                                        release's earlier stages published, before a later one)

``release.yml`` runs these in ``pypi-check`` and in each publishing job. They read the simple
index (PEP 691's JSON), which is what installers read, not the JSON API, which can lead the index
or be cached as missing: a file is served when an installer would find it. A file PyPI has with
another hash than ours is an error: PyPI keeps a version for ever, so a release run that finds one
must not go on as though it had published.
"""

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

INDEX = "https://pypi.org/simple"
Fetch = Callable[[str], bytes | None]
"""Gets a URL's body, or None where it is not found."""


def raw_fetch(url: str) -> bytes | None:
    """The body of a PyPI simple index page, or None if PyPI has no such project.

    Raises:
        OSError: If PyPI could not be reached, or answered with an error other than not found
            (``urllib.error.HTTPError`` is one).
    """
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.pypi.simple.v1+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def retried(get: Fetch, attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> Fetch:
    """A fetch that tries again, a little later each time, when PyPI can't be reached or errs."""

    def retrying(url: str) -> bytes | None:
        for attempt in range(attempts):
            try:
                return get(url)
            except OSError:
                if attempt + 1 == attempts:
                    raise
                sleep(2.0 * (attempt + 1))
        raise AssertionError("attempts is at least 1")

    return retrying


fetch = retried(raw_fetch)
"""The default: PyPI, with a few tries."""


def normalize(name: str) -> str:
    """A distribution's name as PyPI indexes it (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def split(filename: str) -> tuple[str, str]:
    """The distribution and version a wheel or sdist's filename names.

    The version is as written in the name; it is not normalised as PEP 440 would (``0.1.0.dev0``
    stays so), which is how our own files and PyPI's index spell it.
    """
    if filename.endswith(".whl"):
        name, version, *_ = filename.split("-")
    else:
        name, _, rest = filename.removesuffix(".tar.gz").rpartition("-")
        version = rest
    return normalize(name), version


def served(distribution: str, get: Fetch = fetch) -> dict[str, str] | None:
    """The files PyPI serves for a distribution, by filename, with each one's sha256.

    None if it has no such project.
    """
    body = get(f"{INDEX}/{normalize(distribution)}/")
    if body is None:
        return None
    files: list[dict[str, Any]] = json.loads(body).get("files", [])
    return {found["filename"]: found["hashes"].get("sha256", "") for found in files}


def digest(path: Path) -> str:
    """A file's sha256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(path: Path, get: Fetch = fetch) -> str:
    """``absent``, ``same`` or ``different``: what PyPI has under this file's name."""
    files = served(split(path.name)[0], get) or {}
    if path.name not in files:
        return "absent"
    return "same" if files[path.name] == digest(path) else "different"


def report(directory: Path, get: Fetch = fetch) -> list[str]:
    """One line for each file in a directory: ``absent``, ``same`` or ``different`` on PyPI."""
    lines: list[str] = []
    for path in sorted(directory.iterdir()):
        found = state(path, get)
        lines.append(f"{path.name}: {found}")
    return lines


def unreachable_is_absent(path: Path, get: Fetch) -> str:
    """A file's state; a PyPI that cannot be reached or errs has not served it yet."""
    try:
        return state(path, get)
    except OSError:
        return "absent"


def wait(
    directory: Path,
    get: Fetch = fetch,
    attempts: int = 60,
    sleep: Callable[[float], None] = time.sleep,
    interval: float = 10,
) -> None:
    """Wait until PyPI serves each file in a directory, with its hash.

    Raises:
        TimeoutError: If it doesn't within ``attempts`` tries.
        ValueError: If PyPI serves a file of that name with another hash.
    """
    pending = sorted(directory.iterdir())
    for attempt in range(attempts):
        states = {path: unreachable_is_absent(path, get) for path in pending}
        different = [path.name for path, found in states.items() if found == "different"]
        if different:
            raise ValueError(f"PyPI serves {', '.join(different)} with another hash than built")
        pending = [path for path, found in states.items() if found == "absent"]
        if not pending:
            return
        if attempt + 1 < attempts:
            sleep(interval)
    raise TimeoutError("PyPI does not serve " + ", ".join(path.name for path in pending))


def require(requirements: Sequence[str], get: Fetch = fetch) -> list[str]:
    """The ``name==version`` requirements PyPI does not serve a file of."""
    missing: list[str] = []
    for requirement in requirements:
        name, _, version = requirement.partition("==")
        files = served(name, get) or {}
        if not any(split(filename) == (normalize(name), version) for filename in files):
            missing.append(requirement)
    return missing


def main(
    argv: Sequence[str], get: Fetch = fetch, sleep: Callable[[float], None] = time.sleep
) -> int:
    """Run a command; the exit status is 1 when the check fails."""
    command, *rest = argv
    if command == "report":
        try:
            lines = report(Path(rest[0]), get)
        except OSError as error:
            sys.stderr.write(f"pypi: PyPI could not be read: {error}\n")
            return 1
        sys.stdout.write("".join(f"{line}\n" for line in lines))
        different = [line for line in lines if line.endswith(": different")]
        if different:
            sys.stderr.write("pypi: PyPI has these under another hash than the files built\n")
        return 1 if different else 0
    if command == "wait":
        try:
            wait(Path(rest[0]), get)
        except (TimeoutError, ValueError) as error:
            sys.stderr.write(f"pypi: {error}\n")
            return 1
        return 0
    if command == "require":
        try:
            missing = require(rest, retried(get, sleep=sleep))
        except OSError as error:
            sys.stderr.write(f"pypi: PyPI could not be read: {error}\n")
            return 1
        if missing:
            sys.stderr.write(f"pypi: PyPI does not serve {', '.join(missing)}, which come first\n")
        return 1 if missing else 0
    sys.stderr.write(f"pypi: no command {command}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
