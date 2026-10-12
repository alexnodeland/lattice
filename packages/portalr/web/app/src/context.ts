/** What every route can reach: the deployment, who is signed in, the server's reads, and their cache. */

import type { Config, createQueries } from "@portalr/client";
import type { QueryClient } from "@tanstack/react-query";
import type { Signed } from "./signed";

export interface Context {
  readonly config: Config;
  readonly signed: Signed;
  readonly queries: ReturnType<typeof createQueries>;
  readonly queryClient: QueryClient;
}
