import { Page } from "@portalr/ui";
import {
  createRootRouteWithContext,
  type ErrorComponentProps,
  Outlet,
} from "@tanstack/react-router";
import type { Context } from "../context";

export const Route = createRootRouteWithContext<Context>()({
  component: () => (
    <div className="min-h-screen bg-paper p-6 font-sans text-fg">
      <Outlet />
    </div>
  ),
  errorComponent: Failed,
});

/** What a read the server refused, or one that failed, shows. */
function Failed({ error }: ErrorComponentProps) {
  return (
    <Page title="Something went wrong">
      <p role="alert">{error instanceof Error ? error.message : String(error)}</p>
    </Page>
  );
}
