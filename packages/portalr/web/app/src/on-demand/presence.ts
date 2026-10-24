/**
 * A canvas's presence (portalr ADR-0078, artifactr ADR-0093): a connection of its own to the
 * workspace's stream, which asks for no thread's events and watches one diagram; what it says
 * is where the person's pointer is, what they have selected, and what they are changing, and
 * what it hears is the same of everyone else there, stamped by the server with who they are.
 *
 * A connection of the canvas's own, which asks for no events: the page's stream carries those,
 * and presence is the canvas's alone, loaded with it, so the first load holds none of it. It
 * says at most twenty frames a second, and at least one every five, so the others don't think it
 * gone; it connects again after a drop, and watches again.
 */

import type { ExcalidrawElement } from "@excalidraw/excalidraw/element/types";
import type { ArtifactrV1 } from "@portalr/client";

type PeerPresence = ArtifactrV1.PeerPresence;

/** What a canvas says of itself: its pointer, its selection, and what it is changing. */
interface Said {
  readonly baseVersion: number;
  readonly pointer: {
    x: number;
    y: number;
    tool: "pointer" | "laser";
    button: "up" | "down";
  } | null;
  readonly selection: readonly string[];
  readonly editing: readonly Readonly<Record<string, unknown>>[];
}

/** What a canvas hears: everyone else there now, by their connection, and its own rights. */
export interface Heard {
  readonly peers: ReadonlyMap<string, PeerPresence>;
  readonly rights: "view" | "edit" | null;
}

/** A canvas's presence: what it says, and closing it. */
export interface Presence {
  say(said: Said): void;
  close(): void;
}

/** The most frames a canvas says a second, and the longest it is silent. */
const EVERY = 50;
const ALIVE = 5_000;

/** The most bytes a frame may be, under the server's 64 KiB: past it, what is changing is left out. */
const MOST = 60 * 1024;

/**
 * The close codes that end a connection for good, as the server's resolver sends them, 4000 and
 * an HTTP status: not understood, unsigned, refused, or no such workspace. Any other, such as
 * 4429 for a connection that fell behind, or a drop, is asked again after a wait.
 */
const FINAL = new Set([4400, 4401, 4403, 4404]);

/** How long to wait before connecting again, after each drop in a row. */
const BACKOFF = [500, 1_000, 2_000, 5_000];

/** Where the canvas's connection goes, and how it says who it is. */
export interface Line {
  /** The stream's URL, with the person's session, made as each connection is. */
  url(): string;
}

/**
 * Watch a diagram's presence over a connection of the canvas's own: `heard` is told of every
 * change in who is there. The connection is a `WebSocket` unless a test gives its own.
 */
export function watchPresence(
  line: Line,
  diagram: string,
  heard: (now: Heard) => void,
  open: (url: string) => WebSocket = (url) => new WebSocket(url, "artifactr.v1"),
): Presence {
  const peers = new Map<string, PeerPresence>();
  let rights: Heard["rights"] = null;
  /** This connection, as the others know it: its own `peer_left` says its watch ended. */
  let own: string | null = null;
  let socket: WebSocket | null = null;
  let closed = false;
  let drops = 0;
  let seq = 0;
  let last: Said | null = null;
  let sentAt = 0;
  let pending: ReturnType<typeof setTimeout> | null = null;
  let alive: ReturnType<typeof setInterval> | null = null;

  const told = () => heard({ peers: new Map(peers), rights });

  const send = () => {
    pending = null;
    if (last === null || socket?.readyState !== WebSocket.OPEN || rights === null) return;
    sentAt = Date.now();
    seq += 1;
    const frame = {
      type: "presence",
      artifact_id: diagram,
      seq,
      base_version: last.baseVersion,
      pointer: last.pointer,
      selection: last.selection.slice(0, 500),
      // A viewer's would be dropped, and said as an error: it isn't sent.
      editing: rights === "edit" ? last.editing.slice(0, 100) : [],
    };
    let text = JSON.stringify(frame);
    if (text.length > MOST) text = JSON.stringify({ ...frame, editing: [] });
    socket.send(text);
  };

  const connect = () => {
    const current = open(line.url());
    socket = current;
    current.onopen = () => {
      current.send(
        JSON.stringify({ type: "hello", protocol: "artifactr.v1", from_head: true, events: false }),
      );
    };
    current.onmessage = (message) => {
      const frame = JSON.parse(String(message.data)) as { type: string } & Record<string, unknown>;
      if (frame.type === "replay_complete") {
        drops = 0;
        current.send(
          JSON.stringify({
            type: "command",
            command_id: crypto.randomUUID(),
            command: { type: "watch_artifact", artifact_id: diagram },
          }),
        );
      } else if (frame.type === "command_result") {
        const outcome = frame.outcome as {
          type?: string;
          rights?: "view" | "edit";
          peer?: string;
        } | null;
        if (outcome?.type === "watching") {
          rights = outcome.rights ?? "view";
          own = outcome.peer ?? null;
          told();
          send();
        }
      } else if (frame.type === "peer_presence") {
        const peer = frame as unknown as PeerPresence;
        if (peer.artifact_id === diagram) {
          peers.set(peer.peer, peer);
          told();
        }
      } else if (frame.type === "peer_left" && frame.peer === own) {
        // Its watch ended, its rights gone: no one is shown, and nothing is said.
        rights = null;
        own = null;
        peers.clear();
        told();
      } else if (frame.type === "peer_left") {
        if (peers.delete(String(frame.peer))) told();
      }
    };
    current.onclose = (event) => {
      if (socket !== current) return;
      socket = null;
      peers.clear();
      rights = null;
      told();
      // Refused for good, unsigned or not allowed (4401, 4403, 4400): not asked again, as the
      // page's stream isn't; it goes on looking without the others.
      if (closed || FINAL.has(event.code)) return;
      const wait = BACKOFF[Math.min(drops, BACKOFF.length - 1)] ?? 5_000;
      drops += 1;
      setTimeout(() => closed || connect(), wait);
    };
  };

  connect();
  alive = setInterval(() => {
    if (Date.now() - sentAt >= ALIVE) send();
  }, ALIVE / 2);

  return {
    say(said) {
      last = said;
      if (pending !== null) return;
      pending = setTimeout(send, Math.max(0, sentAt + EVERY - Date.now()));
    },
    close() {
      closed = true;
      if (pending !== null) clearTimeout(pending);
      if (alive !== null) clearInterval(alive);
      const current = socket;
      socket = null;
      current?.close(1000);
    },
  };
}

/** A peer's picture: what it is changing, on which version, and who it is. */
export interface Ghost {
  readonly peer: string;
  readonly name: string;
  readonly baseVersion: number;
  readonly elements: readonly ExcalidrawElement[];
}

/**
 * The pictures to draw: each peer's latest `editing`, or, once it stops, its last, until the
 * head moves past the version it was drawn on.
 */
export function ghostsNow(
  kept: ReadonlyMap<string, Ghost>,
  heard: readonly Ghost[],
  head: number,
): Map<string, Ghost> {
  const next = new Map<string, Ghost>();
  for (const ghost of heard) {
    if (ghost.elements.length > 0) {
      next.set(ghost.peer, ghost);
    } else {
      const last = kept.get(ghost.peer);
      if (last !== undefined && last.baseVersion >= head) next.set(ghost.peer, last);
    }
  }
  return next;
}
