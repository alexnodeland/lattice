/** Who is signed in, and which tenant they work in, as every request carries them. */

/** Who is signed in, and which tenant they are working in. */
export interface Session {
  /** The access token Supabase Auth issued, or null when no one is signed in. */
  readonly token: string | null;
  /** The tenant a stream works in, or null outside one. A REST read names its own. */
  readonly tenant: string | null;
}

/** The headers every REST request carries: the token, once there is one. */
export function sessionHeaders(session: Session): Record<string, string> {
  return session.token === null ? {} : { Authorization: `Bearer ${session.token}` };
}

/**
 * A workspace stream's URL: the surface's base, `http(s)://` or `ws(s)://`, and the session in
 * the query, since a browser's WebSocket can't send headers (lattice RFC-0002).
 */
export function streamUrl(
  base: string,
  workspace: string,
  session: { readonly token: string; readonly tenant: string },
): string {
  const url = new URL(
    `${base.replace(/\/$/, "")}/workspaces/${encodeURIComponent(workspace)}/stream`,
  );
  url.protocol = url.protocol.replace(/^http/, "ws");
  url.searchParams.set("access_token", session.token);
  url.searchParams.set("tenant", session.tenant);
  return url.toString();
}
