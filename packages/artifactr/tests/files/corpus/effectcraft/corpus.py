"""EffectCraft's corpus: an `.ecproj` per feature, made by EffectCraft, each feature read out of
its JSON; and the projects made to break it."""

import json
from functools import partial
from typing import Any

from artifactr.files.app import App
from artifactr.files.craft.project import LIMIT
from artifactr.files.effectcraft import Subprocess
from tests.files.corpus.effectcraft.features import read
from tests.files.corpus.effectcraft.make import HERE, MADE
from tests.files.corpus.harness import Corpus, dense

SAID = b'{"savedBy": "0.11.1", "schema": 2'
"""How an `.ecproj` starts, saying which release saved it."""


def kept(content: bytes) -> bytes:
    """EffectCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def held(feature: str) -> dict[str, Any]:
    """A feature's project, to break."""
    return json.loads(MADE.committed(feature))


def comp(project: dict[str, Any]) -> dict[str, Any]:
    """A project's first composition's kind."""
    return next(i["kind"] for i in project["items"].values() if i["kind"]["type"] == "Comp")


def written(project: dict[str, Any]) -> bytes:
    return json.dumps(project).encode()


def not_json() -> bytes:
    """A project that says which release saved it, and then isn't JSON."""
    return SAID + b", nope"


def too_large() -> bytes:
    """A project larger than any that holds no footage."""
    return SAID + b', "pad": "' + b" " * LIMIT + b'"}'


def nested() -> bytes:
    """A project nested far deeper than any EffectCraft writes."""
    return SAID + b', "items": ' + b"[" * 100_000 + b"]" * 100_000 + b"}"


def no_items() -> bytes:
    """A project whose items aren't a project's."""
    return written({**held("solids"), "items": ["Red"]})


def footage(path: str) -> bytes:
    """A project whose solid is footage instead, at a path."""
    project = held("solids")
    red = next(i for i in project["items"].values() if i["name"] == "Red")
    red["kind"] = {"type": "Footage", "path": path, "kind": "Still", "width": 64, "height": 36}
    return written(project)


def future_schema() -> bytes:
    """A project of a schema EffectCraft doesn't know yet."""
    return written({**held("solids"), "schema": 99})


def huge_comp() -> bytes:
    """A composition of 200,000 by 200,000 pixels, which EffectCraft would shrink."""
    project = held("solids")
    comp(project).update(width=200_000, height=200_000)
    return written(project)


def frame_rate() -> bytes:
    """A composition of a billion frames a second, which EffectCraft would slow."""
    project = held("solids")
    comp(project)["frame_rate"] = {"num": 1_000_000_000, "den": 1}
    return written(project)


def unread_layer() -> bytes:
    """A layer whose source is another composition, named without its item."""
    project = held("solids")
    comp(project)["layers"][0]["source"] = {"type": "Comp"}
    return written(project)


def adapter(cli: str, version: str) -> App:
    """EffectCraft's CLI is confined to the call's read and write roots."""
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="effectcraft",
    extension=".ecproj",
    folder=HERE,
    makers=MADE.makers(),
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={
        "not_json": not_json,
        "too_large": too_large,
        "nested": nested,
        "dense": partial(dense, b'{"savedBy": "0.11.1", "schema": 2, "items": ', b"}", LIMIT),
        "no_items": no_items,
        "footage_at_a_path": partial(footage, "/etc/hosts"),
        "footage_up_the_tree": partial(footage, "../../../etc/hosts"),
        "future_schema": future_schema,
        "huge_comp": huge_comp,
        "frame_rate": frame_rate,
        "unread_layer": unread_layer,
    },
)
"""EffectCraft 0.11.1 keeps every feature. An expression that loops forever is ended by
EffectCraft's own limit on its loops, an older schema is opened and saved in the current one, a
composition of 10^15 ticks and items numbered twice are each opened, not refused, so none is a
hostile file here."""
