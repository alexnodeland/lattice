import "@portalr/ui/styles.css";
import {
  type Config,
  createApi,
  createCommands,
  createQueries,
  Refused,
  readConfig,
} from "@portalr/client";
import { Page } from "@portalr/ui";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { routeTree } from "./routeTree.gen";
import { Signed } from "./signed";

/** Whether the server refused a read because no one is signed in, or they may not. */
const refusedFor = (error: unknown, ...statuses: number[]) =>
  error instanceof Refused && statuses.includes(error.status);

/** Whether the server refused a read for what was asked: asking again would get the same. */
const refusedOutright = (error: unknown) =>
  error instanceof Refused && error.status >= 400 && error.status < 500;

function start(root: Root, config: Config) {
  const signed = new Signed(config, () => {
    queryClient.clear();
    void router.navigate({ to: "/sign-in" });
  });
  const queryClient = new QueryClient({
    // A read refused as unsigned ends the session, which goes back to signing in.
    queryCache: new QueryCache({
      onError: (error) => {
        if (refusedFor(error, 401)) {
          void signed.signOut();
        }
      },
    }),
    defaultOptions: {
      queries: { retry: (count, error) => !refusedOutright(error) && count < 3 },
    },
  });
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
    <Page title="portalr can't start">
      <p role="alert">
        The deployment's settings couldn't be read:{" "}
        {error instanceof Error ? error.message : String(error)}.
      </p>
    </Page>,
  );
}
