/**
 * Who is signed in, through Supabase Auth's client alone (portalr ADR-0014), and the token every
 * request and stream carries.
 */

import type { Config, Session, StreamSession } from "@portalr/client";
import { GoTrueClient } from "@supabase/auth-js";
import { authUrl } from "./deployment";

/** What a session did that a stream must follow: its token was refreshed, or it ended. */
export type Change = "refreshed" | "ended";

export class Signed {
  readonly auth: GoTrueClient;
  private current: { readonly token: string; readonly user: string } | null = null;
  private readonly watchers = new Set<(change: Change) => void>();

  /** `onSignedOut` runs when the session ends: here, in another tab, or as it expires. */
  constructor(config: Config, onSignedOut: () => void) {
    this.auth = new GoTrueClient({
      url: authUrl(config.supabase.url, location.origin),
      headers: { apikey: config.supabase.key },
      storageKey: "portalr",
      persistSession: true,
      autoRefreshToken: true,
    });
    this.auth.onAuthStateChange((event, session) => {
      this.current = session && { token: session.access_token, user: session.user.id };
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
    this.current = session && { token: session.access_token, user: session.user.id };
    return this.current?.user ?? null;
  }

  /** End the session in this browser alone: another tab's or device's stays. */
  signOut(): Promise<unknown> {
    return this.auth.signOut({ scope: "local" });
  }

  /** Calls `watcher` each time the session is refreshed or ends, until the returned function is. */
  watch(watcher: (change: Change) => void): () => void {
    this.watchers.add(watcher);
    return () => this.watchers.delete(watcher);
  }

  private tell(change: Change): void {
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
