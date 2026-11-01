import type { Api, Artifactr } from "@portalr/client";
import { SelectField } from "@portalr/ui";
import { choose } from "@portalr/ui/testing";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { remembered } from "../model-memory";
import { AnsweredBy, ModelPicker } from "./model-picker";

const MODELS = [
  { id: "default", label: "Default", family: "", local: false, reasoning: false },
  { id: "fast", label: "Fast", family: "", local: false, reasoning: false },
  { id: "deep", label: "Deep", family: "anthropic", local: false, reasoning: true },
];

/** An API whose models' read answers `listed`, or refuses; and the workspaces it was asked of. */
function api(listed: readonly (typeof MODELS)[number][] | null) {
  const asked: unknown[] = [];
  const GET = vi.fn(async (_command: null, _path: string, init: unknown) => {
    asked.push(init);
    return listed === null ? { data: undefined } : { data: { models: listed } };
  });
  return { api: { portalr: { GET } } as unknown as Api, asked };
}

const withQueries = (children: ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
);

/** The picker as a thread's page holds it: the model chosen, which a test reads. */
function Thread({
  place,
  thread = "thr_1",
  running = false,
  chosen,
}: {
  place: { api: Api; tenant: string; workspace: string };
  thread?: string;
  running?: boolean;
  chosen: (model: string | null) => void;
}) {
  const [model, setModel] = useState<string | null>(null);
  return (
    <ModelPicker
      place={place}
      thread={thread}
      value={model}
      onChange={(next) => {
        setModel(next);
        chosen(next);
      }}
      running={running}
      Select={SelectField}
    />
  );
}

afterEach(() => localStorage.clear());

test("the picker lists the workspace's models, starts on the default, and names no model for it", async () => {
  const { api: read, asked } = api(MODELS);
  const chosen = vi.fn();
  const place = { api: read, tenant: "acme", workspace: "main" };
  const screen = await render(withQueries(<Thread place={place} chosen={chosen} />));
  const picker = screen.getByRole("combobox", { name: "Model" });
  await expect.element(picker).toHaveTextContent("Default");
  expect(chosen).toHaveBeenLastCalledWith(null);
  expect(asked).toEqual([
    { headers: { "X-Tenant": "acme" }, params: { query: { workspace: "main" } } },
  ]);
  await choose(screen, "Model", "Deep · thinks first");
  expect(chosen).toHaveBeenLastCalledWith("deep");
  await choose(screen, "Model", "Default");
  expect(chosen).toHaveBeenLastCalledWith(null);
});

test("each thread remembers its own model here, and starts on it", async () => {
  const place = { api: api(MODELS).api, tenant: "acme", workspace: "main" };
  const first = await render(withQueries(<Thread place={place} chosen={vi.fn()} />));
  await choose(first, "Model", "Fast");
  expect(remembered("thr_1")).toBe("fast");
  expect(remembered("thr_2")).toBeNull();
  await first.unmount();
  const chosen = vi.fn();
  const again = await render(withQueries(<Thread place={place} chosen={chosen} />));
  await expect.element(again.getByRole("combobox", { name: "Model" })).toHaveTextContent("Fast");
  expect(chosen).toHaveBeenLastCalledWith("fast");
  await again.unmount();
  const other = await render(withQueries(<Thread place={place} thread="thr_2" chosen={vi.fn()} />));
  await expect.element(other.getByRole("combobox", { name: "Model" })).toHaveTextContent("Default");
});

test("a remembered model the workspace no longer allows is the default's", async () => {
  localStorage.setItem("portalr:model:thr_1", "gone");
  const chosen = vi.fn();
  const place = { api: api(MODELS).api, tenant: "acme", workspace: "main" };
  const screen = await render(withQueries(<Thread place={place} chosen={chosen} />));
  await expect
    .element(screen.getByRole("combobox", { name: "Model" }))
    .toHaveTextContent("Default");
  expect(chosen).toHaveBeenLastCalledWith(null);
});

test("while a turn runs the picker is disabled, and says why", async () => {
  const place = { api: api(MODELS).api, tenant: "acme", workspace: "main" };
  const screen = await render(withQueries(<Thread place={place} running chosen={vi.fn()} />));
  const picker = screen.getByRole("combobox", { name: "Model" });
  await expect.element(picker).toBeDisabled();
  await expect.element(picker).toHaveAccessibleDescription("The running turn keeps its model");
});

test("one model, or none read, offers no choice", async () => {
  for (const listed of [MODELS.slice(0, 1), null]) {
    const place = { api: api(listed).api, tenant: "acme", workspace: "main" };
    const chosen = vi.fn();
    const screen = await render(withQueries(<Thread place={place} chosen={chosen} />));
    await vi.waitFor(() => expect(chosen).toHaveBeenCalledWith(null));
    expect(screen.container.textContent).toBe("");
    await screen.unmount();
  }
});

const run = (asked?: string, model?: string) =>
  ({ asked, model, live: { usage: { model: "claude-sonnet" } } }) as unknown as Artifactr.Run;

test("a turn that answered with another model than it asked for says so, quietly", async () => {
  const place = { api: api(MODELS).api, tenant: "acme", workspace: "main" };
  const screen = await render(withQueries(<AnsweredBy place={place} run={run("deep")} />));
  await expect
    .element(screen.getByText("Deep wasn't used: answered by claude-sonnet"))
    .toBeVisible();
});

test("a turn that answers as asked says nothing", async () => {
  const place = { api: api(MODELS).api, tenant: "acme", workspace: "main" };
  const screen = await render(withQueries(<AnsweredBy place={place} run={run("deep", "deep")} />));
  expect(screen.container.textContent).toBe("");
});

test("a workspace that leaves the default out starts on the first model it allows", async () => {
  const chosen = vi.fn();
  const place = { api: api(MODELS.slice(1)).api, tenant: "acme", workspace: "main" };
  const screen = await render(withQueries(<Thread place={place} chosen={chosen} />));
  await expect.element(screen.getByRole("combobox", { name: "Model" })).toHaveTextContent("Fast");
  expect(chosen).toHaveBeenLastCalledWith("fast");
  await choose(screen, "Model", "Deep · thinks first");
  expect(chosen).toHaveBeenLastCalledWith("deep");
});
