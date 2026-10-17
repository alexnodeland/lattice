"""The app port: a native application, run headless, that edits a file by its own commands.

[`App`][artifactr_files.app.App] is the port, and [`FakeApp`][artifactr_files.app.FakeApp] the
fake that every pull request's tests run with. Adapters for real apps come in later phases of
lattice RFC-0003, starting with WordCraft's.
"""

from artifactr_files.app.fake import FakeApp
from artifactr_files.app.port import (
    App,
    AppCommand,
    AppFailed,
    Applied,
    CommandSpec,
    Failure,
    Inspection,
)

__all__ = [
    "App",
    "AppCommand",
    "AppFailed",
    "Applied",
    "CommandSpec",
    "Failure",
    "FakeApp",
    "Inspection",
]
