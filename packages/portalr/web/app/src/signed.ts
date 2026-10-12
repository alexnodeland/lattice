/**
 * Who is signed in, through Supabase Auth's client alone (lattice RFC-0002), and the session
 * every request carries: the current access token, and the tenant the route names.
 */

import type { Session } from "@portalr/client";
import { GoTrueClient } from "@supabase/auth-js";
import { authUrl, type Config } from "./deployment";

export class Signed {
  readonly auth: GoTrueClient;
  private token: string | null = null;
  /** The tenant the current route works in, or null outside one. */
  tenant: string | null = null;

  constructor(config: Config) {
    this.auth = new GoTrueClient({
      url: authUrl(config.supabase.url, location.origin),
      headers: { apikey: config.supabase.key },
      storageKey: "portalr",
      persistSession: true,
      autoRefreshToken: true,
    });
    this.auth.onAuthStateChange((_event, session) => {
      this.token = session?.access_token ?? null;
    });
  }

  /** Whether someone is signed in, once the stored session has been read. */
  async signedIn(): Promise<boolean> {
    const { data } = await this.auth.getSession();
    this.token = data.session?.access_token ?? null;
    return this.token !== null;
  }

  /** The session a request carries now. */
  session(): Session {
    return { token: this.token ?? "", tenant: this.tenant };
  }
}
