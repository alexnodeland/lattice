/** What every route can reach: who is signed in, the server's reads, and their cache. */

import type { createQueries } from "@portalr/client";
import type { QueryClient } from "@tanstack/react-query";
import type { Signed } from "./signed";

export interface Context {
  readonly signed: Signed;
  readonly queries: ReturnType<typeof createQueries>;
  readonly queryClient: QueryClient;
}
