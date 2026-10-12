import { Page, TextLink } from "@portalr/ui";
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
    <div className="min-h-screen bg-paper p-6 font-sans text-fg">
      <HeadContent />
      <Outlet />
    </div>
  ),
  errorComponent: Failed,
  notFoundComponent: NotFound,
});

/** What a read the server refused, or one that failed, shows. */
function Failed({ error }: ErrorComponentProps) {
  return (
    <Page title="Something went wrong">
      <p role="alert">{error instanceof Error ? error.message : String(error)}</p>
    </Page>
  );
}

function NotFound() {
  return (
    <Page title="Not found">
      <p>There's nothing at this address.</p>
      <TextLink render={<Link to="/" />}>Start again</TextLink>
    </Page>
  );
}
