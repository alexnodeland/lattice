/**
 * admin as a route, over a stubbed server, for the route-level tests: alice is signed in, owns
 * acme, and grantr allows her what a test says there; a test's own `serve` answers the rest.
 */

import {
  type Config,
  createApi,
  createCommands,
  createQueries,
  createQueryClient,
  Signed,
} from "@portalr/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { vi } from "vitest";
import { render } from "vitest-browser-react";
import { routeTree } from "../routeTree.gen";

const CONFIG: Config = {
  supabase: { url: "http://127.0.0.1:9", key: "sb_publishable_x" },
  surfaces: { artifactr: "/artifactr/v1", reflexr: "/reflexr/v1", grantr: "", portalr: "" },
  readers: { tempo: false },
};

/** alice, signed in, as Supabase Auth would say, without asking it. */
class Alice extends Signed {
  override signedIn = async () => "alice";
  override email = () => "alice@example.com";
}

/** A test's answers, past who alice is and what grantr allows her: undefined for none. */
export type Serve = (request: Request, path: string) => Promise<Response | undefined>;

/** The server: alice's memberships and checks, then `serve`'s answers, then a refusal. */
function server(allowed: readonly string[], serve: Serve, tenants: readonly string[]) {
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname;
    if (path === "/grantr/v1/me") {
      return Response.json({
        memberships: tenants.map((tenant) => ({ tenant, user: "alice", roles: ["owner"] })),
      });
    }
    if (path === "/grantr/v1/checks") {
      const asked: { action: string }[] = await request.json();
      return Response.json(asked.map(({ action }) => allowed.includes(action)));
    }
    return (await serve(request, path)) ?? Response.json({ detail: "not here" }, { status: 403 });
  };
}

/**
 * admin, opened at `path`, with grantr allowing `allowed` in each of `tenants`, acme alone unless
 * a test names more: its screen and its router.
 */
export async function open(
  path: string,
  allowed: readonly string[],
  serve: Serve,
  tenants: readonly string[] = ["acme"],
) {
  vi.stubGlobal("fetch", vi.fn(server(allowed, serve, tenants)));
  const queryClient = createQueryClient(() => undefined);
  const api = createApi(CONFIG.surfaces, () => ({ token: "t0k3n" }));
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: {
      config: CONFIG,
      signed: new Alice(CONFIG, () => undefined),
      queries: createQueries(api),
      commands: createCommands(api, () => undefined),
      queryClient,
    },
  });
  const screen = await render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { screen, router };
}
