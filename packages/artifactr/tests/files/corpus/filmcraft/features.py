"""Each feature of a `.fcproj`, read out of its JSON into a value two saves compare by.

A value keeps what the feature means, by name rather than by FilmCraft's numbering, and leaves
out what a save may write out again without changing it, such as an item's label colour. The
fidelity report opens and saves each corpus file in FilmCraft and compares its feature's value
before and after (lattice RFC-0003, phase 2).
"""

import json
from collections.abc import Callable, Iterator
from typing import Any, Final

Value = list[tuple[object, ...]]
Node = dict[str, Any]

PLACES: Final = 3
"""The decimals a number is compared to: a save writes floats its own way."""


class Project:
    """A `.fcproj`'s project: its items by number, and its sequences."""

    def __init__(self, content: bytes) -> None:
        self.project: Node = json.loads(content)["project"]
        self.items: dict[str, Node] = self.project["items"]

    def name(self, item: object) -> str:
        return self.items[str(item)]["name"]

    def sequences(self) -> Iterator[tuple[str, Node]]:
        for item in self.items.values():
            if "Sequence" in item["kind"]:
                yield item["name"], item["kind"]["Sequence"]

    def clips(self, kind: str = "video_tracks") -> Iterator[tuple[str, Node]]:
        for _, sequence in self.sequences():
            for track in sequence[kind]:
                for clip in track["items"]:
                    yield track["name"], clip


def value(held: Node) -> object:
    """A parameter's value, out of the one variant it is held in, its numbers rounded."""
    (found,) = held["value"].values()
    if isinstance(found, float):
        return round(found, PLACES)
    if isinstance(found, dict):
        return tuple(round(v, PLACES) for v in found.values())
    return tuple(found) if isinstance(found, list) else found


def params(clip: Node, effect: str, *names: str) -> tuple[object, ...]:
    """The values of some of a clip's effect's parameters."""
    (found,) = (e for e in clip["effects"] if e["effect"] == effect)
    return tuple(value(found["params"][name]) for name in names)


def tree(project: Project, children: list[Node], depth: int = 0) -> Value:
    """Each bin and item, by name, at its depth."""
    found: Value = []
    for child in children:
        if "Bin" in child:
            found.append((depth, child["Bin"]["name"]))
            found += tree(project, child["Bin"]["children"], depth + 1)
        else:
            found.append((depth, project.name(child["Item"])))
    return found


def sequences(project: Project) -> Value:
    return [
        (name, s["settings"]["width"], s["settings"]["height"], s["settings"]["frame_rate"]["num"])
        for name, s in project.sequences()
    ]


def bins(project: Project) -> Value:
    return tree(project, project.project["root"]["children"])


def generated_media(project: Project) -> Value:
    """Each medium FilmCraft generates, by name, and what generates it."""
    return [
        (item["name"], json.dumps(item["kind"]["Media"]["media"]["Generator"], sort_keys=True))
        for item in project.items.values()
        if "Media" in item["kind"]
    ]


def clips(project: Project) -> Value:
    return [
        (track, project.name(clip["item"]), clip["start"], clip["duration"])
        for track, clip in project.clips()
    ]


def transitions(project: Project) -> Value:
    names = {clip["id"]: project.name(clip["item"]) for _, clip in project.clips()}
    return [
        (t["effect"]["effect"], names[t["from"]], names[t["to"]], t["start"], t["duration"])
        for _, sequence in project.sequences()
        for track in sequence["video_tracks"]
        for t in track["transitions"]
    ]


def effects(project: Project) -> Value:
    return [
        (
            clip["name"],
            [e["effect"] for e in clip["effects"]],
            params(clip, "gaussian_blur", "blurriness"),
        )
        for _, clip in project.clips()
    ]


def keyframes(project: Project) -> Value:
    """Each animated parameter's keyframes: their times and values."""
    return [
        (effect["effect"], name, [(k["time"], value(k), k["interp"]) for k in held["keyframes"]])
        for _, clip in project.clips()
        for effect in clip["effects"]
        for name, held in effect["params"].items()
        if held.get("keyframes")
    ]


def titles(project: Project) -> Value:
    return [
        (clip["name"], *params(clip, "graphic_text", "text", "font", "size", "fill_color"))
        for _, clip in project.clips()
    ]


def shapes(project: Project) -> Value:
    return [
        (clip["name"], *params(clip, "graphic_shape", "shape", "size"))
        for _, clip in project.clips()
    ]


def captions(project: Project) -> Value:
    return [
        (track["name"], track["format"], c["text"], c["start"], c["duration"])
        for _, sequence in project.sequences()
        for track in sequence["caption_tracks"]
        for c in track["captions"]
    ]


def markers(project: Project) -> Value:
    return [
        (m["kind"], m["name"], m["comment"], m["start"])
        for _, sequence in project.sequences()
        for m in sequence["markers"]
    ]


def audio(project: Project) -> Value:
    return [
        (track, project.name(clip["item"]), clip["start"], clip["duration"])
        for track, clip in project.clips("audio_tracks")
    ]


def color(project: Project) -> Value:
    return [
        (clip["name"], *params(clip, "lumetri", "input_lut", "look_lut"))
        for _, clip in project.clips()
    ]


READERS: Final[dict[str, Callable[[Project], Value]]] = {
    "sequences": sequences,
    "bins": bins,
    "generated_media": generated_media,
    "clips": clips,
    "transitions": transitions,
    "effects": effects,
    "keyframes": keyframes,
    "titles": titles,
    "shapes": shapes,
    "captions": captions,
    "markers": markers,
    "audio": audio,
    "color": color,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.fcproj`."""
    return READERS[feature](Project(content))
