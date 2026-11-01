/**
 * The models a person may choose for a turn (portalr ADR-0086, artifactr ADR-0097). Apart from
 * the queries every page holds, so that only the thread's page, which offers the choice, carries
 * it: the first page's bytes don't.
 */

import type { Run } from "./artifactr";
import type { components as Portalr } from "./generated/portalr.openapi";
import type { Api } from "./rest";

/** A model a workspace allows, as the server lists it. */
export type OfferedModel = Portalr["schemas"]["OfferedModel"];

/**
 * The models a person may choose for a turn in a workspace, in the application's order: those
 * its `models:allowed` lets them use, which the runner checks again. Kept five minutes, and not
 * tried again: a refusal, or one model, offers no choice. Its key is under the tenant's.
 */
export const models = (api: Api, tenant: string, workspace: string) =>
  ({
    queryKey: ["portalr", tenant, "models", workspace] as const,
    queryFn: async () => {
      // The tenant named as every read names it, with no helper the first page would carry.
      const { data } = await api.portalr.GET(null, "/portalr/v1/models", {
        headers: { "X-Tenant": tenant },
        params: { query: { workspace } },
      });
      // Refused, or not there: no choice is offered, and the composer is as it was.
      if (data === undefined) {
        throw new Error("the models couldn't be read");
      }
      return data.models;
    },
    staleTime: 5 * 60_000,
    retry: false,
    refetchOnWindowFocus: false,
  }) as const;

/**
 * The model the message that made a run's latest start asked for, where the run doesn't answer
 * with it: the runner fell back to the default, and posted a notice why. Null where it answers as
 * asked, or where nothing was asked: a resumed run is judged by its reply, whose model it takes.
 */
export function fellBack(run: Run): string | null {
  return run.asked && run.asked !== run.model ? run.asked : null;
}
