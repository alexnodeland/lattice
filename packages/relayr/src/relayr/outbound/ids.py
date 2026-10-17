"""Derived ids: what a run's writes are made once by, in artifactr and in a tracker alike.

A write's id is a digest of the run, its last checkpoint, what the write is, and how many such
writes the attempt made before it (relayr ADR-0019). A retried attempt that makes the same
writes, in any order, derives the same ids.
"""

import hashlib
import json
from collections import Counter
from typing import Any

from pydantic import JsonValue

from reflexr.workspace import Reaction


class Derivation:
    """Derives the ids of one attempt's writes, the same on every attempt that makes them."""

    def __init__(self, reaction: Reaction[Any]) -> None:
        self._reaction = reaction
        self._made: Counter[tuple[int, str, str]] = Counter()

    def derive(self, op: str, *key: str) -> str:
        """The digest a write's ids are made from, the same on every attempt that makes it.

        It is made of the run, its segment, what the write is, and how many such writes the
        attempt made before it.
        """
        run = self._reaction.run
        what = "\x00".join(key)
        made = (run.checkpoints, op, what)
        seed = f"{run.id}\x00{run.checkpoints}\x00{op}\x00{what}\x00{self._made[made]}"
        self._made[made] += 1
        return hashlib.sha256(seed.encode()).hexdigest()[:16]


def canonical(value: JsonValue) -> str:
    """A digest of JSON data, the same for equal data."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()
