import { FailureAlert, NewVersionOffer, Plain, TextLink } from "@portalr/ui";
import {
  createRootRouteWithContext,
  type ErrorComponentProps,
  HeadContent,
  Link,
  Outlet,
} from "@tanstack/react-router";
import type { Context } from "../context";

export const Route = createRootRouteWithContext<Context>()({
  head: ({ match }) => ({ meta: [{ title: match.context.title() }] }),
  component: () => (
    <>
      <HeadContent />
      <Outlet />
      {/* After the page, so its skip link stays the first stop of the keyboard. */}
      <NewVersionOffer ui="app" page={import.meta.env.BASE_URL} />
    </>
  ),
  errorComponent: Failed,
  notFoundComponent: NotFound,
});

/** What a read the server refused, or one that failed, shows. */
function Failed({ error }: ErrorComponentProps) {
  return (
    <Plain home={<Link to="/" />} title="Something went wrong">
      <FailureAlert error={error} />
      <TextLink render={<Link to="/" />}>Start again</TextLink>
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
