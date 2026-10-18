"""The test application's hosted editor: a stand-in for an app's browser build, on its own origin.

WordCraft's build is 40 MB, so the scenarios serve a stand-in in its shape, through artifactr's
``editor_app``, as a deployment serves the real one: a page whose inline script is allowed by its
hash, its own script, named by a hash, and the WebAssembly that compiles. compose runs it as a
service of its own, on a port of its own, so it is another origin than the portal's. Nightly
serves WordCraft's own build the same way (artifactr's ``test_pilot_live.py``).
"""

from pathlib import Path

from artifactr.files.fastapi import editor_app

app = editor_app(Path(__file__).parent / "editor")
