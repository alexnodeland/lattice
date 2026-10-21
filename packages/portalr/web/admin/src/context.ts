/**
 * What every route can reach: the deployment, who is signed in, the server's reads and their cache,
 * and the commands sent over REST.
 */

import type { Config, createCommands, createQueries, Signed } from "@portalr/client";
import type { QueryClient } from "@tanstack/react-query";

export interface Context {
  readonly config: Config;
  readonly signed: Signed;
  readonly queries: ReturnType<typeof createQueries>;
  readonly commands: ReturnType<typeof createCommands>;
  readonly queryClient: QueryClient;
  /** A page's title: what it is, outermost last, then the UI's name, the kit's or portalr's. */
  readonly title: (...parts: string[]) => string;
}
