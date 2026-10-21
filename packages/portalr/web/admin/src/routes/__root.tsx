import { Alert, failureSaid, NewVersionOffer, Plain, pageTitle, TextLink } from "@portalr/ui";
import {
  createRootRouteWithContext,
  type ErrorComponentProps,
  HeadContent,
  Link,
  Outlet,
} from "@tanstack/react-router";
import type { Context } from "../context";

export const Route = createRootRouteWithContext<Context>()({
  head: ({ match }) => ({ meta: [{ title: pageTitle(match.context.config.brand, "admin") }] }),
  component: () => (
    <>
      <HeadContent />
      <Outlet />
      {/* After the page, so its skip link stays the first stop of the keyboard. */}
      <NewVersionOffer ui="admin" page={import.meta.env.BASE_URL} />
    </>
  ),
  errorComponent: Failed,
  notFoundComponent: NotFound,
});

/** What a read the server refused, or one that failed, shows. */
function Failed({ error }: ErrorComponentProps) {
  return (
    <Plain ui="admin" home={<Link to="/" />} title="Something went wrong">
      <Alert tone="error">{failureSaid(error)}</Alert>
    </Plain>
  );
}

function NotFound() {
  return (
    <Plain ui="admin" home={<Link to="/" />} title="Not found">
      <p>There's nothing at this address.</p>
      <TextLink render={<Link to="/" />}>Start again</TextLink>
    </Plain>
  );
}
