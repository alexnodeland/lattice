import "@portalr/ui/styles.css";
import { createApi, createQueries } from "@portalr/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loadConfig } from "./deployment";
import { routeTree } from "./routeTree.gen";
import { Signed } from "./signed";

const config = await loadConfig();
const signed = new Signed(config);
const queryClient = new QueryClient();
const router = createRouter({
  routeTree,
  basepath: import.meta.env.BASE_URL,
  context: {
    signed,
    queries: createQueries(createApi(config.surfaces, () => signed.session())),
    queryClient,
  },
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html has no #root");
}
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
