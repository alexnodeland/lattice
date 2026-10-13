import "@portalr/ui/styles.css";
import {
  type Config,
  createApi,
  createQueries,
  createQueryClient,
  readConfig,
  Signed,
} from "@portalr/client";
import { Plain } from "@portalr/ui";
import { QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { routeTree } from "./routeTree.gen";

/**
 * admin: the UI for a tenant's owners and admins, and the deployment's operators (lattice
 * RFC-0002). It shares the app's session, so signing in to either signs in to both.
 */
function start(root: Root, config: Config) {
  const signed = new Signed(config, () => {
    queryClient.clear();
    void router.navigate({ to: "/sign-in" });
  });
  // A read refused as unsigned ends the session, which goes back to signing in.
  const queryClient = createQueryClient(() => void signed.signOut());
  const router = createRouter({
    routeTree,
    basepath: import.meta.env.BASE_URL,
    context: {
      config,
      signed,
      queries: createQueries(createApi(config.surfaces, () => signed.session())),
      queryClient,
    },
  });
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
  return router;
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof start>;
  }
}

const element = document.getElementById("root");
if (!element) {
  throw new Error("index.html has no #root");
}
const root = createRoot(element);
try {
  start(root, await readConfig(location.origin));
} catch (error) {
  root.render(
    <Plain
      ui="admin"
      home={<a href={import.meta.env.BASE_URL} />}
      title="portalr admin can't start"
    >
      <p role="alert">
        The deployment's settings couldn't be read:{" "}
        {error instanceof Error ? error.message : String(error)}.
      </p>
    </Plain>,
  );
}
