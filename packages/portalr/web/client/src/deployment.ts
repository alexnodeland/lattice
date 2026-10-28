/**
 * Where mini apps and the editors are for the portal at the address this page is at (portalr
 * ADR-0084). A deployment reached at several addresses is several portal origins: `config.json`
 * names the canonical one, `origin`, and by each other, `aliases`, the apps' origin and the
 * editors beside it, which that address reaches. At an alias, its place; at the canonical origin,
 * or where the deployment names none, the canonical apps and editors; anywhere else, nothing runs
 * and nothing is framed, since the sandbox and the shim answer only the portals they were told.
 */

import type { Config } from "./rest";

export interface Deployment {
  readonly apps: string | null;
  readonly editors: Readonly<Record<string, string>>;
  /** Each connected app's address, by its integration. */
  readonly links: Readonly<Record<string, string>>;
  /** Whether the deployment serves apps and editors at this address: false where it names none. */
  readonly known: boolean;
}

/** The apps' origin and the editors for the portal at `at`, such as `location.origin`. */
export function deploymentAt(config: Config, at: string): Deployment {
  const alias = config.aliases[at];
  if (alias !== undefined) {
    return { apps: alias.apps ?? null, editors: alias.editors, links: alias.links, known: true };
  }
  if (!config.origin || config.origin === at) {
    return { apps: config.apps, editors: config.editors, links: config.links, known: true };
  }
  return { apps: null, editors: {}, links: {}, known: false };
}

/** The portal's addresses the deployment serves apps and editors at, canonical first. */
export function portalsOf(config: Config): string[] {
  return [...(config.origin ? [config.origin] : []), ...Object.keys(config.aliases)];
}
