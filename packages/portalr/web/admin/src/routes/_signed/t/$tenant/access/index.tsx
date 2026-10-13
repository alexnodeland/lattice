import { createFileRoute, notFound, redirect } from "@tanstack/react-router";
import { accessIn, PARTS } from "../../../../../access";

/** Access opens on its first part grantr allows; with none, there is no Access here. */
export const Route = createFileRoute("/_signed/t/$tenant/access/")({
  loader: async ({ context, params }) => {
    const checks = accessIn(context.queries, params.tenant);
    const allowed = checks.select(await context.queryClient.ensureQueryData(checks));
    const first = PARTS.find(({ reads }) => allowed.has(reads));
    if (first === undefined) {
      throw notFound();
    }
    throw redirect({ to: `/t/$tenant/access/${first.part}`, params });
  },
});
