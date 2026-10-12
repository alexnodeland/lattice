/** Who is signed in, and which tenant they work in, as every request carries them. */

/** Who is signed in, and which tenant they are working in. */
export interface Session {
  /** The access token Supabase Auth issued. */
  readonly token: string;
  /** The active tenant's id, or null before one is chosen: grantr then answers for every one. */
  readonly tenant: string | null;
}

/** The headers every REST request carries: the token, and the active tenant once there is one. */
export function sessionHeaders(session: Session): Record<string, string> {
  const token = { Authorization: `Bearer ${session.token}` };
  return session.tenant === null ? token : { ...token, "X-Tenant": session.tenant };
}

/**
 * A workspace stream's URL: the surface's base, `http(s)://` or `ws(s)://`, and the session in
 * the query, since a browser's WebSocket can't send headers (lattice RFC-0002).
 */
export function streamUrl(
  base: string,
  workspace: string,
  session: Session & { readonly tenant: string },
): string {
  const url = new URL(
    `${base.replace(/\/$/, "")}/workspaces/${encodeURIComponent(workspace)}/stream`,
  );
  url.protocol = url.protocol.replace(/^http/, "ws");
  url.searchParams.set("access_token", session.token);
  url.searchParams.set("tenant", session.tenant);
  return url.toString();
}
