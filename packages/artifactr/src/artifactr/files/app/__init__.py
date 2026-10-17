"""The app port: a native application, run headless, that edits a file by its own commands.

[`App`][artifactr.files.app.App] is the port, and [`FakeApp`][artifactr.files.app.FakeApp] the
fake that every pull request's tests run with. Each real app's adapter is a layer of its own,
starting with WordCraft's, `artifactr.files.wordcraft`.
"""

from artifactr.files.app.fake import FakeApp
from artifactr.files.app.port import (
    App,
    AppCommand,
    AppFailed,
    Applied,
    CommandSpec,
    Failure,
    Inspection,
    Talk,
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
    "Talk",
]
