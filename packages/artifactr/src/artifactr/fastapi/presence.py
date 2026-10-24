"""Presence: who has an artifact open, and where, passed between connections and never stored.

A connection that watches an artifact joins its room, keyed by tenant, workspace and artifact,
and hears the others there; what it says is passed on as each peer's latest frame (lattice
RFC-0006, artifactr ADR-0093). :class:`PresenceChannel` is the port; :class:`LocalPresence`, its
default, keeps the rooms in this process, as ``FanoutChannel`` keeps runs' live frames, so an
application that runs one process needs nothing else. A peer silent for :data:`SILENT` seconds
is announced as having left, the next time anyone in its room speaks; it is still told of the
others, and is back as soon as it speaks again.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

from artifactr.core import (
    ArtifactId,
    InvalidState,
    PeerLeft,
    PeerPresence,
    TenantId,
    WorkspaceId,
)

__all__ = ["MOST_IN_A_ROOM", "SILENT", "Deliver", "LocalPresence", "PresenceChannel", "Room"]

SILENT: Final = 10.0
"""Seconds a peer may say nothing before it is announced as having left."""

MOST_IN_A_ROOM: Final = 50
"""The most peers in one room: each one's every frame goes to all the others."""

type Room = tuple[TenantId, WorkspaceId, ArtifactId]
"""Whose presence is passed where: a tenant's workspace's artifact."""

type Deliver = Callable[[PeerPresence | PeerLeft, str], None]
"""What a peer is told: a frame for its connection to send, with its JSON, made once for every
peer told it. It must not block."""


class PresenceChannel(Protocol):
    """Passes presence between the peers in a room, in this process or across several."""

    def join(self, room: Room, peer: str, deliver: Deliver) -> list[PeerPresence]:
        """Join a room, to be told of the others there; answer with what each last said.

        Raises:
            InvalidState: If the room holds :data:`MOST_IN_A_ROOM` peers already.
        """
        ...

    def say(self, room: Room, frame: PeerPresence) -> None:
        """Tell the others in a room what a peer says now.

        Each peer's frames reach every other in the order the peer said them: a watcher keeps
        only the latest it was told, as the latest said.
        """
        ...

    def leave(self, room: Room, peer: str) -> None:
        """Leave a room: the others are told, and the peer is told nothing more."""
        ...


@dataclass
class _Peer:
    deliver: Deliver
    heard: float
    last: PeerPresence | None = None
    """What it last said, while it is present: None once it is announced as having left."""


class LocalPresence:
    """Rooms in this process: every connection to it shares them."""

    def __init__(
        self, *, clock: Callable[[], float] = time.monotonic, most: int = MOST_IN_A_ROOM
    ) -> None:
        self._clock = clock
        self._most = most
        self._rooms: dict[Room, dict[str, _Peer]] = {}

    def join(self, room: Room, peer: str, deliver: Deliver) -> list[PeerPresence]:
        """Join a room, to be told of the others there; answer with what each last said.

        Raises:
            InvalidState: If the room holds as many peers as it may already.
        """
        peers = self._rooms.setdefault(room, {})
        if peer not in peers and len(peers) >= self._most:
            raise InvalidState(f"at most {self._most} may have one artifact open at once")
        self._sweep(room)
        here = [other.last for other in peers.values() if other.last is not None]
        peers[peer] = _Peer(deliver, heard=self._clock())
        return here

    def say(self, room: Room, frame: PeerPresence) -> None:
        """Tell the others in a room what a peer says now, and who has fallen silent."""
        peers = self._rooms.get(room, {})
        speaker = peers.get(frame.peer)
        if speaker is None:
            return  # a peer that left, or never joined, says nothing
        speaker.last, speaker.heard = frame, self._clock()
        self._sweep(room)
        text = frame.model_dump_json()
        for name, other in list(peers.items()):
            if name != frame.peer:
                other.deliver(frame, text)

    def leave(self, room: Room, peer: str) -> None:
        """Leave a room: the others are told, and the peer is told nothing more."""
        peers = self._rooms.get(room, {})
        if peers.pop(peer, None) is None:
            return
        self._told_left(room, peer)
        if not peers:
            del self._rooms[room]

    def _sweep(self, room: Room) -> None:
        """Announce the peers in a room that have fallen silent as having left."""
        peers = self._rooms[room]
        now = self._clock()
        for name, peer in list(peers.items()):
            if peer.last is not None and now - peer.heard > SILENT:
                peer.last = None
                self._told_left(room, name)

    def _told_left(self, room: Room, peer: str) -> None:
        left = PeerLeft(artifact_id=room[2], peer=peer)
        text = left.model_dump_json()
        for name, other in list(self._rooms.get(room, {}).items()):
            if name != peer:
                other.deliver(left, text)
