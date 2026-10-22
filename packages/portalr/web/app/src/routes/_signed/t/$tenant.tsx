import { createFileRoute, Outlet } from "@tanstack/react-router";

/** A tenant: grantr says who the caller is in it, and every read under it names it. */
export const Route = createFileRoute("/_signed/t/$tenant")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`${params.tenant}`) }],
  }),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.me(params.tenant)),
  component: Outlet,
});
