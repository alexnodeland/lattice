import {
  FailureAlert,
  NewVersionOffer,
  Plain,
  TextLink,
  useHeadingAfterNavigation,
} from "@portalr/ui";
import {
  createRootRouteWithContext,
  type ErrorComponentProps,
  HeadContent,
  Link,
  Outlet,
  useRouter,
} from "@tanstack/react-router";
import { useCallback } from "react";
import type { Context } from "../context";

export const Route = createRootRouteWithContext<Context>()({
  head: ({ match }) => ({ meta: [{ title: match.context.title() }] }),
  component: () => (
    <>
      <FocusAfterNavigation />
      <HeadContent />
      <Outlet />
      {/* After the page, so its skip link stays the first stop of the keyboard. */}
      <NewVersionOffer ui="admin" page={import.meta.env.BASE_URL} />
    </>
  ),
  errorComponent: Failed,
  notFoundComponent: NotFound,
});

/** After a page changes inside the app, the focus goes to its heading (portalr ADR-0068). */
function FocusAfterNavigation() {
  const router = useRouter();
  useHeadingAfterNavigation(useCallback((on) => router.subscribe("onResolved", on), [router]));
  return null;
}

/** What a read the server refused, or one that failed, shows. */
function Failed({ error }: ErrorComponentProps) {
  return (
    <Plain ui="admin" home={<Link to="/" />} title="Something went wrong">
      <FailureAlert error={error} />
      <TextLink render={<Link to="/" />}>Start again</TextLink>
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
