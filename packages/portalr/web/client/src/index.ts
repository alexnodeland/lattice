/**
 * @portalr/client: the only code in portalr's UIs that talks to the server.
 *
 * It grows into the generated types, the fetch client and the WebSocket stores in phase 3 of
 * portalr's RFC-0001.
 */

/** Who is signed in, and which tenant they are working in. */
export interface Session {
  /** The access token Supabase Auth issued. */
  readonly token: string;
  /** The active tenant's id. */
  readonly tenant: string;
}

/** The headers every REST request carries: the token, and the active tenant. */
export function sessionHeaders(session: Session): Record<string, string> {
  return { Authorization: `Bearer ${session.token}`, "X-Tenant": session.tenant };
}
