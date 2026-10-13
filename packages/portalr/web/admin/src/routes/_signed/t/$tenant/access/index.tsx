import { createFileRoute, notFound, redirect } from "@tanstack/react-router";
import { allowedNow, PARTS } from "../../../../../access";

/** Access opens on its first part grantr allows; with none, there is no Access here. */
export const Route = createFileRoute("/_signed/t/$tenant/access/")({
  beforeLoad: async ({ context, params }) => {
    const allowed = await allowedNow(context, params.tenant);
    const first = PARTS.find(({ reads }) => allowed.has(reads));
    if (first === undefined) {
      throw notFound();
    }
    throw redirect({ to: `/t/$tenant/access/${first.part}`, params });
  },
});
