/**
 * Product analytics' capture (lattice RFC-0008), loaded once a person says yes: someone who never
 * does never loads it. Their events go to portalr's relay alone.
 *
 * Nothing is sent until the person says yes, and nothing is captured on its own: a screen names
 * an event, from the relay's registry, with the router's own name for the route it is on, never
 * the address in the bar. Events wait in memory, a few at a time, and go in one batch, under a
 * session id portalr signed for the person; a batch that fails is dropped, never retried, so
 * analytics never slows or fails a screen.
 */

import type { Api } from "@portalr/client";

/** An event a screen records: a name in the relay's registry, the route, and its props. */
export interface AnalyticsEvent {
  readonly event: string;
  /** The router's name for the route, such as `/t/$tenant/w/$workspace/runs`. */
  readonly route?: string;
  readonly props?: Readonly<Record<string, string>>;
}

/** How many events wait before they are sent at once. */
export const BATCH = 10;

/** How long an event waits, in milliseconds, before what has gathered is sent. */
export const WAIT = 5_000;

/**
 * A person's events, gathered and sent to the relay in the tenant `tenant`, under a session id
 * portalr signs for them when the first batch goes. Made only after the person says yes.
 */
export class Capture {
  private readonly waiting: AnalyticsEvent[] = [];
  private session: Promise<string | null> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;

  private readonly api: Api;
  private readonly tenant: string;
  private readonly carry: (session: string | null) => void;
  private readonly wait: number;

  /**
   * `carry` is handed the signed session while it is held, and null once it isn't, for every
   * request to carry (portalr ADR-0073); `wait` is how long a few events wait before they go,
   * `WAIT` unless a test says otherwise.
   */
  constructor(
    api: Api,
    tenant: string,
    carry: (session: string | null) => void = () => {},
    wait: number = WAIT,
  ) {
    this.api = api;
    this.tenant = tenant;
    this.carry = carry;
    this.wait = wait;
  }

  /** Gather an event, sending what has gathered when there are enough, or after a while. */
  record(event: AnalyticsEvent): void {
    if (this.closed) {
      return;
    }
    this.waiting.push(event);
    if (this.waiting.length >= BATCH) {
      void this.flush();
    } else if (this.timer === null) {
      this.timer = setTimeout(() => void this.flush(), this.wait);
    }
  }

  /**
   * Stop, as the person says no or leaves the tenant: what waits is dropped, unsent, and nothing
   * is sent after.
   */
  close(): void {
    this.closed = true;
    this.waiting.length = 0;
    this.carry(null);
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  /** Send what has gathered now; anything the relay doesn't take is dropped. */
  async flush(): Promise<void> {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const events = this.waiting.splice(0, BATCH);
    if (events.length === 0 || this.closed) {
      return;
    }
    // A session the relay no longer takes, as one past its hours, is signed afresh, once.
    for (let tries = 0; tries < 2 && !this.closed; tries += 1) {
      const session = await this.signed();
      if (session === null || this.closed) {
        return;
      }
      if (await this.send(session, events)) {
        break;
      }
      this.session = null;
    }
    if (this.waiting.length > 0) {
      void this.flush();
    }
  }

  /** The session portalr signed for this capture, asked for once; null if it couldn't be. */
  private async signed(): Promise<string | null> {
    this.session ??= this.api.portalr
      .POST(null, "/portalr/v1/analytics/session")
      .then(({ data }) => data?.session ?? null)
      .catch(() => null);
    const session = await this.session;
    if (session === null) {
      this.session = null;
    }
    this.carry(this.closed ? null : session);
    return session;
  }

  /** Send a batch: false only where the relay refused its session, true otherwise. */
  private async send(session: string, events: readonly AnalyticsEvent[]): Promise<boolean> {
    try {
      const { response } = await this.api.portalr.POST(null, "/portalr/v1/events", {
        headers: { "X-Tenant": this.tenant },
        body: { session, events: [...events] },
      });
      return response.status !== 403;
    } catch {
      return true; // Dropped: analytics never fails a screen.
    }
  }
}
