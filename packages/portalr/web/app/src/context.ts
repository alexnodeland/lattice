/**
 * What every route can reach: the deployment, who is signed in, the server's reads and their cache,
 * and the commands sent over REST.
 */

import type { Config, createCommands, createQueries } from "@portalr/client";
import type { QueryClient } from "@tanstack/react-query";
import type { Signed } from "./signed";

export interface Context {
  readonly config: Config;
  readonly signed: Signed;
  readonly queries: ReturnType<typeof createQueries>;
  readonly commands: ReturnType<typeof createCommands>;
  readonly queryClient: QueryClient;
}
