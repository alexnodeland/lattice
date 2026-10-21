"""Each feature of a `.scraft`, read out of its JSON into a value two saves compare by.

A value keeps what the feature means, by name rather than by SoundCraft's numbering, and leaves
out what a save may write out again without changing it, such as a track's height. The fidelity
report opens and saves each corpus file in SoundCraft and compares its feature's value before
and after (lattice RFC-0003, phase 2).
"""

import json
from collections.abc import Callable
from typing import Any, Final

Value = list[tuple[object, ...]]
Node = dict[str, Any]

PLACES: Final = 3
"""The decimals a number is compared to: a save writes floats its own way."""


def number(value: float) -> float:
    return round(float(value), PLACES)


def tracks(session: Node) -> Value:
    return [
        (t["name"], t["kind"], (t.get("instrument") or {}).get("plugin")) for t in session["tracks"]
    ]


def midi(session: Node) -> Value:
    """Each MIDI clip's place, and its notes."""
    return [
        (
            track["name"],
            clip["name"],
            clip["start"],
            clip["length"],
            [
                (n["pitch"], n["velocity"], n["start"], n["length"])
                for n in clip["content"]["Midi"]["sequence"]["notes"]
            ],
        )
        for track in session["tracks"]
        for playlist in track["playlists"]
        for clip in playlist["clips"]
    ]


def instruments(session: Node) -> Value:
    return [
        (t["name"], t["instrument"]["plugin"], t["instrument"]["preset"])
        for t in session["tracks"]
        if t.get("instrument")
    ]


def mixer(session: Node) -> Value:
    return [
        (
            t["name"],
            number(t["mixer"]["volume_db"]),
            tuple(map(number, t["mixer"]["pan"])),
            t["mixer"]["mute"],
        )
        for t in session["tracks"]
    ]


def inserts(session: Node) -> Value:
    """Each insert's slot and plugin, and its parameters."""
    return [
        (t["name"], slot, insert["plugin"], sorted(insert["params"].items()))
        for t in session["tracks"]
        for slot, insert in enumerate(t["mixer"]["inserts"])
        if insert
    ]


def sends(session: Node) -> Value:
    busses = {bus["id"]: bus["name"] for bus in session["busses"]}
    return [
        (t["name"], slot, busses[send["target"]["Bus"]], number(send["level_db"]))
        for t in session["tracks"]
        for slot, send in enumerate(t["mixer"]["sends"])
        if send
    ]


def automation(session: Node) -> Value:
    return [
        (t["name"], lane["param"], [(p["at"], number(p["value"])) for p in lane["points"]])
        for t in session["tracks"]
        for lane in t["automation"]
    ]


def markers(session: Node) -> Value:
    return [(m["name"], m["kind"], m["start"], m["end"]) for m in session["markers"]]


def tempo_and_meter(session: Node) -> Value:
    tempo = session["tempo"]
    return [
        *(("tempo", t["tick"], number(t["bpm"])) for t in tempo["tempos"]),
        *(("meter", m["tick"], m["numerator"], m["denominator"]) for m in tempo["meters"]),
        *(("key", at, key) for at, key in session["key_signatures"]),
    ]


def comments(session: Node) -> Value:
    return [(t["name"], t["comments"]) for t in session["tracks"]]


READERS: Final[dict[str, Callable[[Node], Value]]] = {
    "tracks": tracks,
    "midi": midi,
    "instruments": instruments,
    "mixer": mixer,
    "inserts": inserts,
    "sends": sends,
    "automation": automation,
    "markers": markers,
    "tempo_and_meter": tempo_and_meter,
    "comments": comments,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.scraft`."""
    return READERS[feature](json.loads(content))
