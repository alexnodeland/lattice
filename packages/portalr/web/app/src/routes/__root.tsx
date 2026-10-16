import { failureSaid, Plain, TextLink } from "@portalr/ui";
import {
  createRootRouteWithContext,
  type ErrorComponentProps,
  HeadContent,
  Link,
  Outlet,
} from "@tanstack/react-router";
import type { Context } from "../context";

export const Route = createRootRouteWithContext<Context>()({
  head: () => ({ meta: [{ title: "portalr" }] }),
  component: () => (
    <>
      <HeadContent />
      <Outlet />
    </>
  ),
  errorComponent: Failed,
  notFoundComponent: NotFound,
});

/** What a read the server refused, or one that failed, shows. */
function Failed({ error }: ErrorComponentProps) {
  return (
    <Plain home={<Link to="/" />} title="Something went wrong">
      <p role="alert">{failureSaid(error)}</p>
    </Plain>
  );
}

function NotFound() {
  return (
    <Plain home={<Link to="/" />} title="Not found">
      <p>There's nothing at this address.</p>
      <TextLink render={<Link to="/" />}>Start again</TextLink>
    </Plain>
  );
}
