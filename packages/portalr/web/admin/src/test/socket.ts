/**
 * reflexr's stream, as a test sees it: a WebSocket that answers `hello` with a welcome, the
 * events it is told of and `replay_complete`, and each command with the result a test decides,
 * and with the events that result is to be followed by.
 */

import type { ReflexrV1 } from "@portalr/client";
import { vi } from "vitest";

type Event = ReflexrV1.EventFrame["event"];

/** A frame of the log, as the server sends it. */
export const frame = (
  seq: number,
  event: Event,
  actor: ReflexrV1.EventFrame["actor"] = { kind: "system", name: "reflexr" },
): ReflexrV1.EventFrame =>
  ({
    type: "event",
    seq,
    id: `evt_${seq}`,
    ts: `2026-10-15T09:0${seq % 10}:00Z`,
    workspace_id: "notes",
    actor,
    correlation_id: "c",
    event,
  }) as ReflexrV1.EventFrame;

/** A command the page sent, and the id it sent it under. */
export interface Sent {
  readonly id: string;
  readonly command: { type: string; run_id?: string; reason?: string };
  readonly url: string;
}

/** What a test decides: the log so far, and what a command comes to. */
export interface Script {
  /** Whether the server says nothing to a hello: a workspace that can't be reached. */
  mute?: boolean;
  /** The events a new connection replays. */
  log: ReflexrV1.EventFrame[];
  /** What the server says of a command: a result, and the events that follow it, if any. */
  answer(sent: Sent): {
    result: { ok: boolean; rejection?: { type: string; message?: string } };
    after?: ReflexrV1.EventFrame[];
  } | null;
}

export class FakeSocket {
  static sockets: FakeSocket[] = [];
  static sent: Sent[] = [];
  /** The hellos the page sent: what it asked for. */
  static hellos: { types?: string[] | null; resume_after_seq?: number }[] = [];
  static script: Script = { log: [], answer: () => null };

  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: ((closed: { code: number }) => void) | null = null;
  closed = false;

  readonly url: string;
  readonly protocol: string;

  constructor(url: string, protocol: string) {
    this.url = url;
    this.protocol = protocol;
    FakeSocket.sockets.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  /** Whether the page holds it open. */
  get open() {
    return !this.closed;
  }

  #emit(frame: unknown) {
    if (!this.closed) {
      this.onmessage?.({ data: JSON.stringify(frame) });
    }
  }

  /** The server tells the page of an event, live. */
  push(event: ReflexrV1.EventFrame) {
    this.#emit(event);
  }

  /** The server sends any frame at all, such as an error. */
  raw(frame: unknown) {
    this.#emit(frame);
  }

  /** The connection ends, as a server or a network ends it. */
  end(code: number) {
    this.closed = true;
    this.onclose?.({ code });
  }

  send(data: string) {
    const frame = JSON.parse(data) as {
      type: string;
      command_id?: string;
      command?: Sent["command"];
    };
    if (frame.type === "hello") {
      FakeSocket.hellos.push(frame as never);
      if (FakeSocket.script.mute) {
        return;
      }
      const log = FakeSocket.script.log;
      this.#emit({ type: "welcome", head_seq: log.at(-1)?.seq ?? 0 });
      for (const each of log) {
        this.#emit(each);
      }
      this.#emit({ type: "replay_complete" });
      return;
    }
    const sent: Sent = {
      id: frame.command_id ?? "",
      command: frame.command ?? { type: "" },
      url: this.url,
    };
    FakeSocket.sent.push(sent);
    const answer = FakeSocket.script.answer(sent);
    if (answer === null) {
      return;
    }
    queueMicrotask(() => {
      this.#emit({ type: "command_result", command_id: sent.id, ...answer.result });
      for (const each of answer.after ?? []) {
        this.#emit(each);
      }
    });
  }

  close() {
    this.closed = true;
  }
}

/** Replace WebSocket with the fake, with this script; undo it with `vi.unstubAllGlobals`. */
export function stubSockets(script: Script) {
  FakeSocket.sockets = [];
  FakeSocket.sent = [];
  FakeSocket.hellos = [];
  FakeSocket.script = script;
  vi.stubGlobal("WebSocket", FakeSocket);
}
