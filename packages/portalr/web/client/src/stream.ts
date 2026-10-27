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

/** A frame, as the store acts on it. */
export type Classified<Frame, R extends Result> =
  | { readonly kind: "welcome"; readonly headSeq: number; readonly reset: boolean }
  | { readonly kind: "replay_complete" }
  | { readonly kind: "event"; readonly envelope: Extract<Frame, Envelope> }
  | { readonly kind: "result"; readonly result: R }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "other"; readonly frame: Frame };

/**
 * A command's end.
 *
 * - `done`: it was carried out, now or by an earlier try. For `post_message`, that means the
 *   message was posted, not that its turn ran.
 * - `refused`: the server refused it, with the rejection in `result`.
 * - `closed`: the store was closed before an answer came.
 */
export type Settled<R extends Result> =
  | { readonly outcome: "done" | "refused"; readonly result: R }
  | { readonly outcome: "closed" };

/** One protocol's part: its name, its frames, its reducer, and which commands create by id. */
export interface Protocol<State, Frame, Command, R extends Result> {
  /** The protocol's identifier, which is also the WebSocket subprotocol: `artifactr.v1`. */
  readonly name: string;
  /** The state before any event. */
  initial(): State;
  /** What a frame is, to the store. */
  classify(frame: Frame): Classified<Frame, R>;
  /** The state after one event; the same object if the event changes nothing. */
  apply(state: State, envelope: Extract<Frame, Envelope>): State;
  /** The state after a frame that isn't an event, welcome, result or error, such as a live frame. */
  other(state: State, frame: Frame): State;
  /** Whether the command creates something under an id the client chose. */
  creates(command: Command): boolean;
}

/** Where the store is in its connection's life. */
export type Status = "connecting" | "replaying" | "live" | "closed";

/** What a component reads. */
export interface Snapshot<State> {
  readonly state: State;
  /** The last `seq` applied: the store's position in the log. */
  readonly seq: number;
  readonly status: Status;
  /** The last `error` frame's message: a frame the server couldn't parse, or a failed command. */
  readonly error: string | null;
}

/** Close codes after which reconnecting by itself can't help (both protocols' 4400, 4401, 4403). */
const FINAL = new Set([4400, 4401, 4403]);

/** The most to wait before each reconnect, in milliseconds; the last repeats. Full jitter. */
const BACKOFF = [100, 500, 1000, 2000, 5000];

/** The fields a hello frame carries that the store sets itself. */
type Handshake = "type" | "protocol" | "resume_after_seq" | "from_head";

export interface StreamOptions<Hello> {
  /** The stream's URL, `ws://` or `wss://`, read at every connect, as `streamUrl` makes it. */
  readonly url: () => string;
  /** The hello's own fields, such as artifactr's `threads` or reflexr's `types`. */
  readonly hello?: Omit<Hello, Handshake>;
  /** Where to resume from: the last `seq` of a tail already read over REST. */
  readonly after?: number;
  /** Start at the log's head, replaying nothing, on the first connect; resume from there after. */
  readonly fromHead?: boolean;
}

interface Pending<Command, R extends Result> {
  readonly command: Command;
  sent: number;
  settle(settled: Settled<R>): void;
}

export class Stream<State, Frame, Command, R extends Result, Hello> {
  readonly protocol: Protocol<State, Frame, Command, R>;
  readonly options: StreamOptions<Hello>;
  #current: Snapshot<State>;
  #socket: WebSocket | null = null;
  #attempt = 0;
  #stopped = true;
  #fromHead: boolean;
  #timer: ReturnType<typeof setTimeout> | null = null;
  readonly #listeners = new Set<() => void>();
  readonly #live = new Set<(envelope: Extract<Frame, Envelope>) => void>();
  readonly #refused = new Set<(result: R) => void>();
  readonly #pending = new Map<string, Pending<Command, R>>();

  /** A store, closed until `open`; `state` is what a tail read over REST built, if any. */
  constructor(
    protocol: Protocol<State, Frame, Command, R>,
    options: StreamOptions<Hello>,
    state: State = protocol.initial(),
  ) {
    this.protocol = protocol;
    this.options = options;
    this.#fromHead = options.fromHead ?? false;
    this.#current = { state, seq: options.after ?? 0, status: "closed", error: null };
  }

  /** The current snapshot; a new object whenever anything in it changes. */
  readonly snapshot = (): Snapshot<State> => this.#current;

  /** Calls `listener` after every change, until the returned function is called. */
  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  /**
   * Calls `listener` with each event applied once the store is live, until the returned function
   * is called: what changes after the reads a screen made, not the replay that caught up to them.
   */
  readonly onLiveEvent = (listener: (envelope: Extract<Frame, Envelope>) => void): (() => void) => {
    this.#live.add(listener);
    return () => this.#live.delete(listener);
  };

  /**
   * Calls `listener` with the server's answer to each command of this store's that it refused,
   * until the returned function is called: a refusal that says something changed, such as an
   * integration turned off, can make a read stale, whichever screen sent the command.
   */
  readonly onRefused = (listener: (result: R) => void): (() => void) => {
    this.#refused.add(listener);
    return () => this.#refused.delete(listener);
  };

  /** Connects, and keeps reconnecting after drops, until `close`. */
  open(): void {
    if (this.#stopped) {
      this.#stopped = false;
      this.#connect();
    }
  }

  /**
   * Connects again now, on a new connection, whatever the store's state: after the session's token
   * is refreshed, say, or after the server refused the old one (4401). A field, as `snapshot` and
   * `subscribe` are, so a page can hand it on detached, as a button's handler.
   */
  readonly reconnect = (): void => {
    this.#stopped = false;
    this.#detach();
    this.#connect();
  };

  /** Closes the connection for good, and settles every unanswered command as `closed`. */
  close(): void {
    this.#stopped = true;
    this.#detach();
    this.#settleAll();
    this.#update({ status: "closed" });
  }

  /** Settles every unanswered command as `closed`. */
  #settleAll(): void {
    for (const pending of this.#pending.values()) {
      pending.settle({ outcome: "closed" });
    }
    this.#pending.clear();
  }

  /**
   * Sends a command, now if connected and otherwise once reconnected, and settles on its end: when
   * it is answered, or when the store is closed, which includes the server refusing it for good.
   */
  send(command: Command, commandId: string = crypto.randomUUID()): Promise<Settled<R>> {
    if (this.#stopped || this.#current.status === "closed") {
      return Promise.resolve({ outcome: "closed" });
    }
    return new Promise((settle) => {
      this.#pending.set(commandId, { command, sent: 0, settle });
      if (this.#current.status === "replaying" || this.#current.status === "live") {
        this.#transmit(commandId);
      }
    });
  }

  /** Forgets the current socket and any pending reconnect, so nothing from them reaches the store. */
  #detach(): void {
    if (this.#timer) {
      clearTimeout(this.#timer);
      this.#timer = null;
    }
    const socket = this.#socket;
    this.#socket = null;
    socket?.close(1000);
  }

  #connect(): void {
    this.#update({ status: "connecting" });
    const socket = new WebSocket(this.options.url(), this.protocol.name);
    this.#socket = socket;
    socket.onopen = () => {
      const position = this.#fromHead
        ? { from_head: true }
        : { resume_after_seq: this.#current.seq };
      socket.send(
        JSON.stringify({
          ...this.options.hello,
          type: "hello",
          protocol: this.protocol.name,
          ...position,
        }),
      );
    };
    socket.onmessage = (message) => {
      if (this.#socket === socket) {
        this.#receive(JSON.parse(String(message.data)) as Frame);
      }
    };
    socket.onclose = (closed) => {
      if (this.#socket !== socket) {
        return; // a socket the store already let go of
      }
      this.#socket = null;
      if (this.#stopped || FINAL.has(closed.code)) {
        // Nothing will answer what is still unanswered: no one waits for it for ever.
        this.#settleAll();
        this.#update({ status: "closed" });
        return;
      }
      const ceiling = BACKOFF[Math.min(this.#attempt, BACKOFF.length - 1)] ?? 0;
      this.#attempt += 1;
      this.#update({ status: "connecting" });
      this.#timer = setTimeout(() => {
        this.#timer = null;
        this.#connect();
      }, Math.random() * ceiling);
    };
  }

  #receive(frame: Frame): void {
    const classified = this.protocol.classify(frame);
    switch (classified.kind) {
      case "welcome": {
        if (this.#fromHead) {
          this.#fromHead = false;
          this.#update({ seq: classified.headSeq, status: "replaying" });
        } else if (classified.reset) {
          this.#update({ state: this.protocol.initial(), seq: 0, status: "replaying" });
        } else {
          this.#update({ status: "replaying" });
        }
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
        const { envelope } = classified;
        if (envelope.seq <= this.#current.seq) {
          return; // already applied: a frame sent twice, or a replay overlapping a tail
        }
        this.#update({
          state: this.protocol.apply(this.#current.state, envelope),
          seq: envelope.seq,
        });
        if (this.#current.status === "live") {
          for (const listener of this.#live) {
            listener(envelope);
          }
        }
        return;
      }
      case "result":
        this.#settle(classified.result);
        return;
      case "error":
        this.#update({ error: classified.message });
        return;
      case "other":
        this.#update({ state: this.protocol.other(this.#current.state, classified.frame) });
        return;
      default:
        classified satisfies never;
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
      result.rejection?.type === "invalid_state" &&
      result.rejection.reason === "already_exists";
    const done = result.ok || madeEarlier;
    pending.settle({ outcome: done ? "done" : "refused", result });
    if (!done) {
      for (const listener of this.#refused) {
        listener(result);
      }
    }
  }

  #update(change: Partial<Snapshot<State>>): void {
    const next = { ...this.#current, ...change };
    if (
      next.state === this.#current.state &&
      next.seq === this.#current.seq &&
      next.status === this.#current.status &&
      next.error === this.#current.error
    ) {
      return;
    }
    this.#current = next;
    for (const listener of this.#listeners) {
      listener();
    }
  }
}
