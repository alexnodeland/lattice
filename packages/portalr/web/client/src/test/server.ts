/**
 * A scripted stream server, on Bun.serve, that speaks the handshake both protocols share: `hello`,
 * `welcome`, the replay after the client's `seq`, `replay_complete`, then events as the test
 * appends them. A test drops connections, resets the log, and decides how each command is
 * answered.
 */

import type { Server, ServerWebSocket } from "bun";

export interface Hello {
  readonly protocol: string;
  readonly resume_after_seq: number;
}

/** How the server answers a command: with a result, or by dropping the connection first. */
export type Answer = { readonly ok: true } | { readonly rejection: string } | "drop";

export class ScriptedServer {
  readonly hellos: Hello[] = [];
  readonly commands: string[] = [];
  #log: { seq: number; event: Record<string, unknown> }[] = [];
  readonly #sockets = new Set<ServerWebSocket<unknown>>();
  readonly #server: Server<unknown>;
  #answers: Answer[] = [];

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

  /** Appends an event, and sends it to every client past its replay. */
  append(event: Record<string, unknown>): void {
    const entry = { seq: this.head + 1, event };
    this.#log.push(entry);
    for (const socket of this.#sockets) {
      socket.send(JSON.stringify(this.#frame(entry)));
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

  /** How the next commands are answered, in order; after them, each is `{ ok: true }`. */
  answer(...answers: Answer[]): void {
    this.#answers.push(...answers);
  }

  stop(): void {
    this.#server.stop(true);
  }

  #frame(entry: { seq: number; event: Record<string, unknown> }) {
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
      const hello = frame as unknown as Hello;
      this.hellos.push(hello);
      const reset = hello.resume_after_seq > this.head;
      const after = reset ? 0 : hello.resume_after_seq;
      socket.send(
        JSON.stringify({ type: "welcome", workspace_id: "ws_1", head_seq: this.head, reset }),
      );
      for (const entry of this.#log.filter((entry) => entry.seq > after)) {
        socket.send(JSON.stringify(this.#frame(entry)));
      }
      socket.send(JSON.stringify({ type: "replay_complete", up_to_seq: this.head }));
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
}
