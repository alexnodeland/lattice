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

/** The headers every REST request carries: the token, once there is one. */
export function sessionHeaders(session: Session): Record<string, string> {
  return session.token === null ? {} : { Authorization: `Bearer ${session.token}` };
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
