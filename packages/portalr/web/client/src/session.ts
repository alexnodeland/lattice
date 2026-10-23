/** Who is signed in, as every request carries them, and a stream, which names its tenant too. */

/** Who is signed in. A REST read names its tenant itself. */
export interface Session {
  /** The access token Supabase Auth issued, or null when no one is signed in. */
  readonly token: string | null;
}

/** What a workspace's stream carries: the current token, and the tenant it works in. */
export interface StreamSession {
  /** The access token, or null once no one is signed in, which the server refuses. */
  readonly token: string | null;
  readonly tenant: string;
}

/**
 * The analytics session portalr signed for the person, while they share how they use the app;
 * null otherwise. Each request carries it, so the server can mark its trace with the session
 * where it is the person's own (portalr ADR-0073).
 */
// Module state, not a Session field: the capture add-on sets it after it loads, and every client
// made before then must carry it too, without each being made again.
let analytics: string | null = null;

/** Set, or with null clear, the analytics session every request carries. */
export function carryAnalyticsSession(signed: string | null): void {
  analytics = signed;
}

/** The headers every REST request carries: the token, once there is one, and the analytics session. */
export function sessionHeaders(session: Session): Record<string, string> {
  if (session.token === null) {
    return {};
  }
  const headers: Record<string, string> = { Authorization: `Bearer ${session.token}` };
  if (analytics !== null) {
    headers["X-Portalr-Analytics-Session"] = analytics;
  }
  return headers;
}

/**
 * A workspace stream's URL: the surface's base, `http(s)://` or `ws(s)://`, and the session in
 * the query, since a browser's WebSocket can't send headers (lattice RFC-0002).
 */
export function streamUrl(base: string, workspace: string, session: StreamSession): string {
  const url = new URL(
    `${base.replace(/\/$/, "")}/workspaces/${encodeURIComponent(workspace)}/stream`,
  );
  url.protocol = url.protocol.replace(/^http/, "ws");
  if (session.token !== null) {
    url.searchParams.set("access_token", session.token);
  }
  url.searchParams.set("tenant", session.tenant);
  return url.toString();
}
