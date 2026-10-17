/**
 * A workspace's add-ons, from its integrations as grantr answers them: Mermaid on where it is on,
 * and off, its default, until they are read and where they can't be.
 */

import { createApi, createQueries } from "@portalr/client";
import { Markdown } from "@portalr/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { WorkspaceAddons } from "./workspace";

const FENCE = "```mermaid\nflowchart LR\n  A --> B\n```";
const ON = "Diagrams can't be drawn yet: this is the diagram's source.";
const OFF = "Diagrams are off here: this is the diagram's source.";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A workspace's Markdown, with grantr answering its integrations as `answer` does. */
async function shown(answer: (request: Request) => Promise<Response>) {
  const asked = vi.fn(answer);
  vi.stubGlobal("fetch", asked);
  const queries = createQueries(
    createApi({ artifactr: "/artifactr/v1", reflexr: "/reflexr/v1", grantr: "" }, () => ({
      token: "t0k3n",
    })),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const screen = await render(
    <QueryClientProvider client={queryClient}>
      <WorkspaceAddons queries={queries} tenant="acme" workspace="notes">
        <Markdown>{FENCE}</Markdown>
      </WorkspaceAddons>
    </QueryClientProvider>,
  );
  return { screen, asked };
}

test("Mermaid is on where the workspace's integrations say so, read once", async () => {
  const { screen, asked } = await shown(async () => Response.json({ "markdown:mermaid": true }));
  await expect.element(screen.getByText(ON)).toBeVisible();
  expect(asked).toHaveBeenCalledOnce();
  const [request] = asked.mock.lastCall ?? [];
  expect(request && new URL(request.url).pathname).toBe(
    "/grantr/v1/tenants/acme/workspaces/notes/enabled-integrations",
  );
});

test("where the integrations can't be read, Mermaid is its default, off", async () => {
  const { screen, asked } = await shown(async () => {
    throw new TypeError("Failed to fetch");
  });
  await expect.poll(() => asked.mock.calls.length).toBe(1);
  await expect.element(screen.getByText(OFF)).toBeVisible();
});

test("where grantr fails, Mermaid is its default, off", async () => {
  const { screen } = await shown(async () => new Response("upstream gone", { status: 503 }));
  await expect.element(screen.getByText(OFF)).toBeVisible();
});
