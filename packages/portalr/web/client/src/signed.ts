/**
 * Who is signed in, through Supabase Auth's client alone (portalr ADR-0014), and the token every
 * request and stream carries, for app and admin alike.
 */

import { type Session as AuthSession, GoTrueClient } from "@supabase/auth-js";
import type { Config } from "./rest";
import type { Session, StreamSession } from "./session";

/** The project's own URL, or, when `config.json` names a path, the one at that path on this origin. */
export function authUrl(supabase: string, origin: string): string {
  return new URL("auth/v1", new URL(supabase.replace(/\/?$/, "/"), origin)).toString();
}

/** What the app keeps of a session: its token, and who it is for. */
interface Current {
  readonly token: string;
  readonly user: string;
  readonly email: string | null;
}

const kept = (session: AuthSession | null): Current | null =>
  session && {
    token: session.access_token,
    user: session.user.id,
    email: session.user.email ?? null,
  };

/** What a session did that a stream must follow: its token was refreshed, or it ended. */
export type SessionChange = "refreshed" | "ended";

export class Signed {
  readonly auth: GoTrueClient;
  private current: Current | null = null;
  private readonly watchers = new Set<(change: SessionChange) => void>();

  /**
   * `onSignedOut` runs when the session ends: here, in another tab, or as it expires. app and
   * admin keep one session on their one origin, so signing in to either signs in to both.
   */
  constructor(config: Config, onSignedOut: () => void) {
    this.auth = new GoTrueClient({
      url: authUrl(config.supabase.url, location.origin),
      headers: { apikey: config.supabase.key },
      storageKey: "portalr",
      persistSession: true,
      autoRefreshToken: true,
    });
    this.auth.onAuthStateChange((event, session) => {
      this.current = kept(session);
      if (event === "TOKEN_REFRESHED") {
        this.tell("refreshed");
      }
      if (event === "SIGNED_OUT") {
        this.tell("ended");
        onSignedOut();
      }
    });
  }

  /** Who is signed in, by Supabase Auth's id for them, once the stored session is read; or null. */
  async signedIn(): Promise<string | null> {
    const { data } = await this.auth.getSession();
    const { session } = data;
    this.current = kept(session);
    return this.current?.user ?? null;
  }

  /** The signed-in person's email, as Supabase Auth has it, to name them by; or null. */
  email(): string | null {
    return this.current?.email ?? null;
  }

  /** End the session in this browser alone: another tab's or device's stays. */
  signOut(): Promise<unknown> {
    return this.auth.signOut({ scope: "local" });
  }

  /** Calls `watcher` each time the session is refreshed or ends, until the returned function is. */
  watch(watcher: (change: SessionChange) => void): () => void {
    this.watchers.add(watcher);
    return () => this.watchers.delete(watcher);
  }

  private tell(change: SessionChange): void {
    for (const watcher of this.watchers) {
      watcher(change);
    }
  }

  /** What a workspace's stream in `tenant` carries: the current token, or none once signed out. */
  streamSession(tenant: string): StreamSession {
    return { token: this.current?.token ?? null, tenant };
  }

  /** The session a request carries now: REST reads name their tenant themselves. */
  session(): Session {
    return { token: this.current?.token ?? null };
  }
}
