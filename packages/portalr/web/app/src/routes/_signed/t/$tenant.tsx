import { createFileRoute, Outlet } from "@tanstack/react-router";

/** A tenant: every request under it names it, and grantr says who the caller is in it. */
export const Route = createFileRoute("/_signed/t/$tenant")({
  beforeLoad: ({ context, params }) => {
    context.signed.tenant = params.tenant;
  },
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.me(params.tenant)),
  component: Outlet,
});
