import "@portalr/ui/styles.css";
import {
  type Config,
  createApi,
  createCommands,
  createQueries,
  createQueryClient,
  readConfig,
  Signed,
} from "@portalr/client";
import { Alert, BrandContext, Plain, pageTitle } from "@portalr/ui";
import { QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { routeTree } from "./routeTree.gen";

function start(root: Root, config: Config) {
  const signed = new Signed(config, () => {
    queryClient.clear();
    void router.navigate({ to: "/sign-in" });
  });
  // A read refused as unsigned ends the session, which goes back to signing in.
  const queryClient = createQueryClient(() => void signed.signOut());
  const api = createApi(config.surfaces, () => signed.session());
  const router = createRouter({
    routeTree,
    basepath: import.meta.env.BASE_URL,
    context: {
      config,
      signed,
      queries: createQueries(api),
      // A command refused as unsigned ends the session, as a read does.
      commands: createCommands(api, () => void signed.signOut()),
      queryClient,
      title: (...parts: string[]) => pageTitle(config.brand, "app", ...parts),
    },
  });
  root.render(
    <StrictMode>
      <BrandContext value={config.brand ?? null}>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </BrandContext>
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
    <Plain home={import.meta.env.BASE_URL} title="portalr can't start">
      <Alert tone="error">
        The deployment's settings couldn't be read:{" "}
        {error instanceof Error ? error.message : String(error)}.
      </Alert>
    </Plain>,
  );
}
