/**
 * A scripted stream server, on Bun.serve, that speaks the handshake both protocols share: `hello`,
 * `welcome`, the replay after the client's `seq`, `replay_complete`, then events as the test
 * appends them. A test drops connections, resets the log, cuts a replay short, sends a frame
 * twice, and decides how each command is answered.
 */

import type { Server, ServerWebSocket } from "bun";

export interface Hello {
  readonly protocol: string;
  readonly resume_after_seq?: number;
  readonly from_head?: boolean;
}

/** How the server answers a command: with a result, or by dropping the connection first. */
export type Answer = { readonly ok: true } | { readonly rejection: string } | "drop";

interface Entry {
  readonly seq: number;
  readonly event: Record<string, unknown>;
}

export class ScriptedServer {
  readonly hellos: Hello[] = [];
  readonly commands: string[] = [];
  #log: Entry[] = [];
  readonly #sockets = new Set<ServerWebSocket<unknown>>();
  readonly #server: Server<unknown>;
  #answers: Answer[] = [];
  #waiting: { count: number; resolve: () => void }[] = [];
  /** How many events the next replay sends before the server drops the connection. */
  #cutReplayAfter: number | null = null;

  constructor() {
    this.#server = Bun.serve({
      port: 0,
      fetch: (request, server) =>
        server.upgrade(request, {
          headers: {
            "Sec-WebSocket-Protocol": request.headers.get("Sec-WebSocket-Protocol") ?? "",
          },
          data: undefined,
        })
          ? undefined
          : new Response("a stream", { status: 426 }),
      websocket: {
        open: (socket) => {
          this.#sockets.add(socket);
        },
        close: (socket) => {
          this.#sockets.delete(socket);
        },
        message: (socket, message) => this.#receive(socket, JSON.parse(String(message))),
      },
    });
  }

  get url(): string {
    return `ws://127.0.0.1:${this.#server.port}/v1/workspaces/ws_1/stream`;
  }

  get head(): number {
    return this.#log.at(-1)?.seq ?? 0;
  }

  /** Resolves once the server has received `count` hellos in all. */
  hello(count: number): Promise<void> {
    return new Promise((resolve) => {
      this.#waiting.push({ count, resolve });
      this.#wake();
    });
  }

  /** Appends an event, and sends it to every client past its replay. */
  append(event: Record<string, unknown>): void {
    const entry = { seq: this.head + 1, event };
    this.#log.push(entry);
    this.#broadcast(entry);
  }

  /** Sends an event already in the log again, as a server overlapping two deliveries would. */
  repeat(seq: number): void {
    const entry = this.#log.find((candidate) => candidate.seq === seq);
    if (entry) {
      this.#broadcast(entry);
    }
  }

  /** Sends a frame as it is to every client. */
  send(frame: Record<string, unknown>): void {
    for (const socket of this.#sockets) {
      socket.send(JSON.stringify(frame));
    }
  }

  /** Closes every connection, as a network drop or a server going away would. */
  drop(code = 1001): void {
    for (const socket of this.#sockets) {
      socket.close(code, "dropped");
    }
  }

  /** Replaces the log, as a server whose data was reset; its head may be behind a client's. */
  reset(events: Record<string, unknown>[]): void {
    this.#log = events.map((event, index) => ({ seq: index + 1, event }));
  }

  /** Makes the next replay send `count` events, then drop the connection. */
  cutNextReplay(count: number): void {
    this.#cutReplayAfter = count;
  }

  /** How the next commands are answered, in order; after them, each is `{ ok: true }`. */
  answer(...answers: Answer[]): void {
    this.#answers.push(...answers);
  }

  stop(): void {
    this.#server.stop(true);
  }

  #broadcast(entry: Entry): void {
    for (const socket of this.#sockets) {
      socket.send(JSON.stringify(this.#frame(entry)));
    }
  }

  #wake(): void {
    const ready = this.#waiting.filter((waiting) => this.hellos.length >= waiting.count);
    this.#waiting = this.#waiting.filter((waiting) => this.hellos.length < waiting.count);
    for (const waiting of ready) {
      waiting.resolve();
    }
  }

  #frame(entry: Entry) {
    return {
      type: "event",
      seq: entry.seq,
      id: `evt_${entry.seq}`,
      ts: "2026-10-12T00:00:00Z",
      workspace_id: "ws_1",
      actor: { kind: "user", id: "alice" },
      correlation_id: `evt_${entry.seq}`,
      event: entry.event,
    };
  }

  #receive(socket: ServerWebSocket<unknown>, frame: Record<string, unknown>): void {
    if (frame.type === "hello") {
      this.#hello(socket, frame as unknown as Hello);
      return;
    }
    const commandId = String(frame.command_id);
    this.commands.push(commandId);
    const answer = this.#answers.shift() ?? { ok: true };
    if (answer === "drop") {
      socket.close(1001, "dropped");
      return;
    }
    socket.send(
      JSON.stringify({
        type: "command_result",
        command_id: commandId,
        ...("rejection" in answer
          ? { ok: false, rejection: { type: answer.rejection, message: answer.rejection } }
          : { ok: true, outcome: null }),
      }),
    );
  }

  #hello(socket: ServerWebSocket<unknown>, hello: Hello): void {
    this.hellos.push(hello);
    this.#wake();
    const position = hello.from_head ? this.head : (hello.resume_after_seq ?? 0);
    const reset = position > this.head;
    const after = reset ? 0 : position;
    socket.send(
      JSON.stringify({ type: "welcome", workspace_id: "ws_1", head_seq: this.head, reset }),
    );
    const replay = this.#log.filter((entry) => entry.seq > after);
    const cut = this.#cutReplayAfter;
    this.#cutReplayAfter = null;
    for (const entry of cut === null ? replay : replay.slice(0, cut)) {
      socket.send(JSON.stringify(this.#frame(entry)));
    }
    if (cut !== null) {
      socket.close(1001, "dropped mid-replay");
      return;
    }
    socket.send(JSON.stringify({ type: "replay_complete", up_to_seq: this.head }));
  }
}
