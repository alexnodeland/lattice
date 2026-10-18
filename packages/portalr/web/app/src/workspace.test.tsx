/**
 * A workspace's integrations as grantr answers them: Mermaid on where it is on, and off, its
 * default, until they are read and where they can't be; and `ui`'s, such as forms, by key.
 */

import { createApi, createQueries, INTEGRATIONS, type IntegrationKey } from "@portalr/client";
import { IntegrationsContext, Markdown } from "@portalr/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, use, useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { WorkspaceAddons } from "./workspace";

const FENCE = "```mermaid\nflowchart LR\n  A --> B\n```";
const ON = "Diagrams can't be drawn yet: this is the diagram's source.";
const OFF = "Diagrams are off here: this is the diagram's source.";

afterEach(() => {
  vi.unstubAllGlobals();
});

const UI: readonly IntegrationKey[] = ["ui:forms", "ui:dashboards", "ui:mini-apps"];

/** Whether each of `ui`'s integrations is on, as the parts inside are told. */
function Gates() {
  const isEnabled = use(IntegrationsContext);
  return (
    <ul>
      {UI.map((key) => (
        <li key={key}>{`${key} ${isEnabled(key) ? "on" : "off"}`}</li>
      ))}
    </ul>
  );
}

/** Each of `ui`'s integrations as lattice's registry says it is by default. */
const byDefault = UI.map(
  (key) => `${key} ${INTEGRATIONS.find((known) => known.key === key)?.default ? "on" : "off"}`,
);

/** What is inside a workspace, with grantr answering its integrations as `answer` does. */
async function shown(
  answer: (request: Request) => Promise<Response>,
  inside: ReactNode = <Markdown>{FENCE}</Markdown>,
) {
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
        {inside}
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

test("forms, dashboards and mini apps are on or off as the workspace's integrations say", async () => {
  const { screen } = await shown(
    async () => Response.json({ "ui:forms": false, "ui:mini-apps": true }),
    <Gates />,
  );
  await expect.element(screen.getByText("ui:forms off")).toBeVisible();
  // A key grantr didn't answer for is its default.
  await expect.element(screen.getByText("ui:dashboards on")).toBeVisible();
  await expect.element(screen.getByText("ui:mini-apps on")).toBeVisible();
});

test("where the integrations can't be read, ui's are each the registry's default", async () => {
  const { screen, asked } = await shown(
    async () => new Response("upstream gone", { status: 503 }),
    <Gates />,
  );
  await expect.poll(() => asked.mock.calls.length).toBe(1);
  for (const said of byDefault) {
    await expect.element(screen.getByText(said)).toBeVisible();
  }
});

test("the answer is the same until the integrations are read again, as a form refused as off asks", async () => {
  const answers = new Set<unknown>();
  function Kept() {
    const [renders, setRenders] = useState(0);
    answers.add(use(IntegrationsContext));
    return (
      <button type="button" onClick={() => setRenders(renders + 1)}>
        {`Drawn ${renders + 1}`}
      </button>
    );
  }
  const { screen } = await shown(async () => Response.json({ "ui:forms": false }), <Kept />);
  // The default before the read, then the read's.
  await expect.poll(() => answers.size).toBe(2);
  await screen.getByRole("button").click();
  await expect.element(screen.getByRole("button", { name: "Drawn 2" })).toBeVisible();
  expect(answers.size).toBe(2);
});
