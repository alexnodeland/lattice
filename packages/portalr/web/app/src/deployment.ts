/**
 * The deployment the app runs in: its `config.json`, served beside the app by portalr's router,
 * and where its Supabase Auth answers.
 */

import type { PortalrApi } from "@portalr/client";

export type Config = PortalrApi.components["schemas"]["Config"];

/** Read `config.json`, which portalr's router serves at `/portalr/config.json`. */
export async function loadConfig(): Promise<Config> {
  const response = await fetch(
    new URL("../config.json", new URL(import.meta.env.BASE_URL, location.origin)),
  );
  if (!response.ok) {
    throw new Error(`config.json answered ${response.status}`);
  }
  return (await response.json()) as Config;
}

/**
 * Supabase Auth's URL: the project's, or, when `config.json` names a path, the one at that path on
 * this origin.
 */
export function authUrl(supabase: string, origin: string): string {
  return new URL("auth/v1", new URL(supabase.replace(/\/?$/, "/"), origin)).toString();
}
