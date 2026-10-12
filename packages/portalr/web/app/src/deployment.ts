/** Where the deployment's Supabase Auth answers, from what `config.json` names. */

/** The project's own URL, or, when `config.json` names a path, the one at that path on this origin. */
export function authUrl(supabase: string, origin: string): string {
  return new URL("auth/v1", new URL(supabase.replace(/\/?$/, "/"), origin)).toString();
}
