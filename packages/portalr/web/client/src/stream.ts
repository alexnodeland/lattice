/**
 * A store over one workspace's WebSocket stream, for artifactr's protocol or reflexr's.
 *
 * It says `hello` from the last `seq` it has applied, follows the replay to `replay_complete`, and
 * applies each event to its state through the protocol's reducer, once, in `seq` order. When the
 * connection drops it reconnects and resumes from that `seq`; when `welcome` says `reset`, it
 * discards its state and rebuilds from the replay. Commands carry a `command_id`, and those still
 * unanswered when the connection drops are sent again, with the same id, so the server carries
 * each out once. Components read it through `subscribe` and `snapshot`, as React's
 * `useSyncExternalStore` asks.
 */

/** An envelope from the log: every event frame has its `seq`. */
export interface Envelope {
  readonly type: "event";
  readonly seq: number;
}

/** What a server sends for a command: its id, and whether it was carried out. */
export interface Result {
  readonly type: "command_result";
  readonly command_id: string;
  readonly ok: boolean;
  readonly rejection?: { readonly [key: string]: unknown } | null;
}

/** A command's settled result. `done` is true when it was carried out, now or by an earlier try. */
export interface Settled<R extends Result> {
  readonly done: boolean;
  readonly result: R;
}

/** One protocol's part: its name, its hello, its reducer, and which commands create by id. */
export interface Protocol<State, Frame extends { readonly type: string }, Command> {
  /** The protocol's identifier, which is also the WebSocket subprotocol: `artifactr.v1`. */
  readonly name: string;
  /** The state before any event. */
  initial(): State;
  /** The state after one event; the same object if the event changes nothing. */
  apply(state: State, envelope: Extract<Frame, Envelope>): State;
  /** The state after a frame that isn't an event, welcome or result, such as a live frame. */
  other?(state: State, frame: Frame): State;
  /** Whether the command creates something under an id the client chose. */
  creates(command: Command): boolean;
}

/** Where the store is in its connection's life. */
export type Status = "connecting" | "replaying" | "live" | "closed";

/** What a component reads: the state, the store's position in the log, and its status. */
export interface Snapshot<State> {
  readonly state: State;
  readonly seq: number;
  readonly status: Status;
}

/** Close codes after which reconnecting can't help (both protocols' 4400, 4401 and 4403). */
const FINAL = new Set([4400, 4401, 4403]);

/** How long to wait before each reconnect, in milliseconds; the last repeats. */
const BACKOFF = [100, 500, 1000, 2000, 5000];

interface Pending<Command, R extends Result> {
  readonly command: Command;
  sent: number;
  settle(settled: Settled<R>): void;
}

export interface StreamOptions {
  /** The stream's URL, `ws://` or `wss://`, with the session in its query, as `streamUrl` makes. */
  readonly url: string;
  /** The hello's fields besides its type, protocol and position, such as `threads` or `types`. */
  readonly hello?: Readonly<Record<string, unknown>>;
  /** Where to resume from: the last `seq` of a tail already read over REST. */
  readonly after?: number;
}

export class Stream<State, Frame extends { readonly type: string }, Command, R extends Result> {
  #current: Snapshot<State>;
  #socket: WebSocket | null = null;
  #attempt = 0;
  #stopped = false;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #url: string;
  readonly #listeners = new Set<() => void>();
  readonly #pending = new Map<string, Pending<Command, R>>();
  readonly protocol: Protocol<State, Frame, Command>;
  readonly options: StreamOptions;

  /** A store, closed until `open`; `state` is what a tail read over REST built, if any. */
  constructor(
    protocol: Protocol<State, Frame, Command>,
    options: StreamOptions,
    state: State = protocol.initial(),
  ) {
    this.protocol = protocol;
    this.options = options;
    this.#url = options.url;
    this.#current = { state, seq: options.after ?? 0, status: "closed" };
  }

  /** The current snapshot; a new object whenever anything in it changes. */
  readonly snapshot = (): Snapshot<State> => this.#current;

  /** Calls `listener` after every change, until the returned function is called. */
  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  /** Connects, and keeps reconnecting after drops, until `close`. */
  open(): void {
    this.#stopped = false;
    this.#connect();
  }

  /**
   * Drops the connection and resumes on a new one, as after a network drop: after the session's
   * token is refreshed, say, with a `url` that carries the new one.
   */
  reconnect(url: string = this.options.url): void {
    this.#url = url;
    this.#socket?.close(1000);
  }

  /** Closes the connection for good; unanswered commands stay unanswered. */
  close(): void {
    this.#stopped = true;
    if (this.#timer) {
      clearTimeout(this.#timer);
    }
    this.#socket?.close(1000);
    this.#update({ status: "closed" });
  }

  /** Sends a command, now if connected and otherwise once reconnected, and settles on its result. */
  send(command: Command, commandId: string = crypto.randomUUID()): Promise<Settled<R>> {
    return new Promise((settle) => {
      this.#pending.set(commandId, { command, sent: 0, settle });
      if (this.#current.status === "replaying" || this.#current.status === "live") {
        this.#transmit(commandId);
      }
    });
  }

  #connect(): void {
    this.#update({ status: "connecting" });
    const socket = new WebSocket(this.#url, this.protocol.name);
    this.#socket = socket;
    socket.onopen = () => {
      socket.send(
        JSON.stringify({
          ...this.options.hello,
          type: "hello",
          protocol: this.protocol.name,
          resume_after_seq: this.#current.seq,
        }),
      );
    };
    socket.onmessage = (message) => this.#receive(JSON.parse(String(message.data)) as Frame);
    socket.onclose = (closed) => {
      if (this.#socket !== socket) {
        return;
      }
      this.#socket = null;
      if (this.#stopped || FINAL.has(closed.code)) {
        this.#update({ status: "closed" });
        return;
      }
      const delay = BACKOFF[Math.min(this.#attempt, BACKOFF.length - 1)];
      this.#attempt += 1;
      this.#update({ status: "connecting" });
      this.#timer = setTimeout(() => this.#connect(), delay);
    };
  }

  #receive(frame: Frame): void {
    switch (frame.type) {
      case "welcome": {
        const { reset } = frame as Frame & { reset?: boolean };
        this.#update(
          reset
            ? { state: this.protocol.initial(), seq: 0, status: "replaying" }
            : { status: "replaying" },
        );
        // Commands sent before the drop and still unanswered go again, with their ids.
        for (const id of this.#pending.keys()) {
          this.#transmit(id);
        }
        return;
      }
      case "replay_complete":
        this.#attempt = 0;
        this.#update({ status: "live" });
        return;
      case "event": {
        const envelope = frame as Extract<Frame, Envelope>;
        if (envelope.seq <= this.#current.seq) {
          return; // already applied: a replay overlapping a tail read over REST
        }
        this.#update({
          state: this.protocol.apply(this.#current.state, envelope),
          seq: envelope.seq,
        });
        return;
      }
      case "command_result": {
        this.#settle(frame as unknown as R);
        return;
      }
      default:
        if (this.protocol.other) {
          this.#update({ state: this.protocol.other(this.#current.state, frame) });
        }
    }
  }

  #transmit(commandId: string): void {
    const pending = this.#pending.get(commandId);
    if (!(pending && this.#socket)) {
      return;
    }
    pending.sent += 1;
    this.#socket.send(
      JSON.stringify({ type: "command", command_id: commandId, command: pending.command }),
    );
  }

  #settle(result: R): void {
    const pending = this.#pending.get(result.command_id);
    if (!pending) {
      return;
    }
    this.#pending.delete(result.command_id);
    // A create sent again after a drop, refused because its id is used: the first try made it.
    const madeEarlier =
      pending.sent > 1 &&
      this.protocol.creates(pending.command) &&
      result.rejection?.type === "invalid_state";
    pending.settle({ done: result.ok || madeEarlier, result });
  }

  #update(change: Partial<Snapshot<State>>): void {
    const next = { ...this.#current, ...change };
    if (
      next.state === this.#current.state &&
      next.seq === this.#current.seq &&
      next.status === this.#current.status
    ) {
      return;
    }
    this.#current = next;
    for (const listener of this.#listeners) {
      listener();
    }
  }
}
