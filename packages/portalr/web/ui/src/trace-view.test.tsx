import type { Outline, Row, Said } from "@portalr/client";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { viewport } from "./test/viewport";
import { duration, type Reveal, type Standing, TraceView } from "./trace-view";

/** A span, as a test says it: where it is in the tree, when, and what it holds. */
interface Spec {
  readonly id: string;
  readonly parent: string | null;
  readonly start: number;
  readonly end: number;
  readonly attributes?: Row["attributes"];
  readonly error?: boolean;
  readonly withheld?: readonly string[];
}

const span = (
  id: string,
  parent: string | null,
  start: number,
  end: number,
  attributes: Row["attributes"] = {},
  rest: Partial<Spec> = {},
): Spec => ({ id, parent, start, end, attributes, ...rest });

const KIND: Record<string, Row["kind"]> = {
  invoke_workflow: "workflow",
  chat: "llm",
  execute_tool: "tool",
};

/** An outline from specs given in tree order, as `outline` would lay them out. */
function made(...specs: Spec[]): Outline {
  const depths = new Map<string, number>();
  const rows = specs.map((one): Row => {
    const depth = one.parent === null ? 0 : (depths.get(one.parent) ?? -1) + 1;
    depths.set(one.id, depth);
    const operation = one.attributes?.["gen_ai.operation.name"];
    const input = one.attributes?.["gen_ai.usage.input_tokens"];
    const output = one.attributes?.["gen_ai.usage.output_tokens"];
    return {
      id: one.id,
      name: `span ${one.id}`,
      kind: typeof operation === "string" ? (KIND[operation] ?? "other") : "other",
      depth,
      parent: specs.some((other) => other.parent === one.id),
      parentId: one.parent,
      offset: one.start,
      duration: one.end - one.start,
      error: one.error ?? false,
      model: (one.attributes?.["gen_ai.request.model"] as string | undefined) ?? null,
      tool: (one.attributes?.["gen_ai.tool.name"] as string | undefined) ?? null,
      tokens:
        typeof input === "number" || typeof output === "number"
          ? {
              input: typeof input === "number" ? input : null,
              output: typeof output === "number" ? output : null,
            }
          : null,
      attributes: one.attributes ?? {},
      withheld: one.withheld ?? [],
    };
  });
  const last = Math.max(0, ...specs.map((one) => one.end));
  return { rows, complete: true, duration: last };
}

const TURN = made(
  span("1", null, 0, 100, { "gen_ai.operation.name": "invoke_workflow" }),
  span(
    "2",
    "1",
    10,
    60,
    {
      "gen_ai.operation.name": "chat",
      "gen_ai.request.model": "claude",
      "gen_ai.usage.input_tokens": 120,
      "gen_ai.usage.output_tokens": 30,
    },
    { withheld: ["gen_ai.input.messages", "gen_ai.output.messages"] },
  ),
  span("3", "2", 20, 30, {
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": "publish",
  }),
  span("4", "1", 70, 90, {}, { error: true }),
);

/** A caller's reveal, for a test to steer: where each span stands, and what a read gave. */
function revealing(standing: Record<string, Standing> = {}, parts: Record<string, Said[]> = {}) {
  const ask = vi.fn();
  const reveal: Reveal = {
    standing: (id) => standing[id] ?? "hidden",
    parts: (row) => parts[row.id] ?? [],
    ask,
  };
  return { reveal, ask };
}

const item = (screen: Awaited<ReturnType<typeof render>>, n: string) =>
  screen.getByRole("treeitem", { name: new RegExp(`^span ${n},`) });

test("a trace is a tree of its spans, deepest last, each named with what it is and how long it took", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} reveal={revealing().reveal} />);
  const tree = screen.getByRole("tree", { name: "Spans" });
  await expect.element(tree).toBeVisible();
  const items = tree.getByRole("treeitem").elements();
  expect(items.map((each) => each.getAttribute("aria-label"))).toEqual([
    "span 1, Workflow, 100 ms",
    "span 2, Model call, 50 ms",
    "span 3, Tool, 10 ms",
    "span 4, Span, 20 ms, failed",
  ]);
  expect(items.map((each) => each.getAttribute("aria-level"))).toEqual(["1", "2", "3", "2"]);
  expect(items.map((each) => each.getAttribute("aria-expanded"))).toEqual([
    "true",
    "true",
    null,
    null,
  ]);
  expect(items[1]?.getAttribute("aria-posinset")).toBe("1");
  expect(items[3]?.getAttribute("aria-posinset")).toBe("2");
  expect(items[1]?.getAttribute("aria-setsize")).toBe("2");
  await expect.element(screen.getByText("4 spans in 100 ms")).toBeVisible();
});

test("a trace with fewer spans than it has says so", async () => {
  const screen = await render(
    <TraceView outline={{ ...TURN, complete: false }} reveal={revealing().reveal} />,
  );
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("This trace has more spans than are shown: these are its first.");
});

test("the first span is chosen, and its details are shown; choosing another shows its own", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} reveal={revealing().reveal} />);
  await expect
    .element(screen.getByRole("region", { name: "span 1" }).getByText("Workflow"))
    .toBeVisible();
  await item(screen, "2").click();
  const model = screen.getByRole("region", { name: "span 2" });
  await expect.element(model.getByText("claude").first()).toBeVisible();
  await expect.element(model.getByText("120 in, 30 out")).toBeVisible();
  await expect.element(model.getByText("10 ms into the trace")).toBeVisible();
  await expect.element(item(screen, "2")).toHaveAttribute("aria-selected", "true");
  await item(screen, "4").click();
  await expect
    .element(screen.getByRole("region", { name: "span 4" }).getByText("Failed"))
    .toBeVisible();
  await item(screen, "3").click();
  await expect.element(screen.getByText("publish").first()).toBeVisible();
});

test("the arrow keys walk the tree and fold it", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} reveal={revealing().reveal} />);
  await item(screen, "1").click();
  await userEvent.keyboard("{ArrowDown}");
  await expect.element(item(screen, "2")).toHaveFocus();
  await expect.element(item(screen, "2")).toHaveAttribute("aria-selected", "true");
  await userEvent.keyboard("{ArrowDown}{ArrowDown}");
  await expect.element(item(screen, "4")).toHaveFocus();
  await userEvent.keyboard("{Home}");
  await expect.element(item(screen, "1")).toHaveFocus();
  await userEvent.keyboard("{End}");
  await expect.element(item(screen, "4")).toHaveFocus();
  // Left from a leaf goes to its parent; left from an open parent folds it.
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(item(screen, "1")).toHaveFocus();
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(item(screen, "1")).toHaveAttribute("aria-expanded", "false");
  await expect.element(item(screen, "2")).not.toBeInTheDocument();
  // Right opens it, and again goes to its first child.
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(item(screen, "2")).toBeVisible();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(item(screen, "2")).toHaveFocus();
  // Nothing before the first, nor after the last.
  await userEvent.keyboard("{Home}{ArrowUp}");
  await expect.element(item(screen, "1")).toHaveFocus();
});

test("folding what the chosen span is under moves the choice to what folded, which keeps the tab stop and the details", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} reveal={revealing().reveal} />);
  // The tool is under the model call, which is under the workflow.
  await item(screen, "3").click();
  await expect.element(screen.getByRole("region", { name: "span 3" })).toBeVisible();
  // Folding the workflow from its chevron hides the chosen row.
  (item(screen, "1").element().querySelector("button") as HTMLElement).click();
  await expect.element(item(screen, "1")).toHaveAttribute("aria-expanded", "false");
  await expect.element(item(screen, "3")).not.toBeInTheDocument();
  await expect.element(item(screen, "1")).toHaveAttribute("aria-selected", "true");
  await expect.element(item(screen, "1")).toHaveFocus();
  await expect.element(screen.getByRole("region", { name: "span 1" })).toBeVisible();
  // One tab stop: the chosen row.
  const stops = screen
    .getByRole("treeitem")
    .elements()
    .filter((row) => row.tabIndex === 0);
  expect(stops).toHaveLength(1);
  // The keyboard gets back in where it was: open it, and walk down to the tool.
  await userEvent.keyboard("{ArrowRight}{ArrowDown}{ArrowDown}");
  await expect.element(item(screen, "3")).toHaveFocus();
});

test("only the rows in view are drawn, however long the trace; End goes to the last, and the tree stays a tab stop when the chosen row is scrolled away", async () => {
  await viewport(1280, 900);
  const many = made(
    span("root", null, 0, 10_000),
    ...Array.from({ length: 2000 }, (_, at) => span(`s${at}`, "root", at, at + 1)),
  );
  const screen = await render(<TraceView outline={many} reveal={revealing().reveal} />);
  await expect.element(screen.getByText("2001 spans in 10.00 s")).toBeVisible();
  const drawn = screen.getByRole("treeitem").elements().length;
  expect(drawn).toBeGreaterThan(5);
  expect(drawn).toBeLessThan(60);
  // The first row is chosen: scrolled away from, nothing drawn is a tab stop but the tree itself.
  const tree = screen.getByRole("tree", { name: "Spans" });
  tree.element().scrollTop = 30_000;
  await expect
    .poll(() =>
      screen
        .getByRole("treeitem")
        .elements()
        .some((row) => row.tabIndex === 0),
    )
    .toBe(false);
  expect((tree.element() as HTMLElement).tabIndex).toBe(0);
  // Tabbing in draws the chosen row again, and focuses it.
  (tree.element() as HTMLElement).focus();
  await expect.element(screen.getByRole("treeitem", { name: /^span root,/ })).toHaveFocus();
  // End draws the last row, wherever the view was, and focuses it.
  await userEvent.keyboard("{End}");
  await expect.element(screen.getByRole("treeitem", { name: /^span s1999,/ })).toHaveFocus();
  await expect.element(screen.getByRole("region", { name: "span s1999" })).toBeVisible();
  expect(screen.getByRole("treeitem").elements().length).toBeLessThan(60);
});

test("what a span withheld is asked for by that span, and shown when the caller has read it", async () => {
  await viewport(1280, 900);
  const { reveal, ask } = revealing();
  const screen = await render(<TraceView outline={TURN} reveal={reveal} />);
  await item(screen, "2").click();
  const withheld = screen.getByRole("region", { name: "Withheld" });
  await expect.element(withheld.getByText(/^2 attributes are kept out of the trace/)).toBeVisible();
  await expect
    .element(withheld.getByText("gen_ai.input.messages, gen_ai.output.messages"))
    .toBeVisible();
  await withheld.getByRole("button", { name: "Show what this span withheld" }).click();
  expect(ask).toHaveBeenCalledExactlyOnceWith("2");
  // A span with nothing withheld has no section for it.
  await item(screen, "4").click();
  await expect.element(screen.getByRole("region", { name: "Withheld" })).not.toBeInTheDocument();
});

test("a span's withheld attributes are being read, read, nothing, or couldn't be", async () => {
  await viewport(1280, 900);
  const read: Said[] = [
    { label: "Prompt", text: "hi" },
    { label: "Completion", text: "hello" },
  ];
  const cases: [Standing, Said[], string][] = [
    ["reading", [], "Reading…"],
    ["failed", [], "What this span withheld couldn't be read."],
    ["read", [], "The read returned none of these attributes."],
  ];
  for (const [standing, parts, said] of cases) {
    const { reveal } = revealing({ "2": standing }, { "2": parts });
    const screen = await render(<TraceView outline={TURN} reveal={reveal} />);
    await item(screen, "2").click();
    await expect
      .element(screen.getByRole("region", { name: "Withheld" }).getByText(said))
      .toBeVisible();
    await screen.unmount();
  }
  const { reveal } = revealing({ "2": "read" }, { "2": read });
  const screen = await render(<TraceView outline={TURN} reveal={reveal} />);
  await item(screen, "2").click();
  const shown = screen.getByRole("region", { name: "Withheld" });
  await expect.element(shown.getByText("Prompt")).toBeVisible();
  await expect.element(shown.getByText("hello")).toBeVisible();
  // Another span still has its own to ask for.
  const other = revealing({ "2": "read" }, { "2": read });
  await screen.rerender(
    <TraceView
      outline={made(span("1", null, 0, 5, {}, { withheld: ["x"] }))}
      reveal={other.reveal}
    />,
  );
  await expect
    .element(screen.getByRole("button", { name: "Show what this span withheld" }))
    .toBeVisible();
});

test("a span with nothing withheld has no section for it, and its attributes are listed in order", async () => {
  await viewport(1280, 900);
  const screen = await render(
    <TraceView
      outline={made(span("1", null, 0, 5, { b: "two", a: 1 }))}
      reveal={revealing().reveal}
    />,
  );
  await expect.element(screen.getByRole("region", { name: "Withheld" })).not.toBeInTheDocument();
  const attributes = screen.getByRole("region", { name: "Attributes" });
  expect(
    attributes
      .getByRole("term")
      .elements()
      .map((term) => term.textContent),
  ).toEqual(["a", "b"]);
});

test("a trace with no spans says so; durations are read as people read them", async () => {
  const screen = await render(<TraceView outline={made()} reveal={revealing().reveal} />);
  await expect.element(screen.getByText("This trace has no spans.")).toBeVisible();
  expect([0.2, 12.4, 999, 1000, 2345].map(duration)).toEqual([
    "<1 ms",
    "12 ms",
    "999 ms",
    "1.00 s",
    "2.35 s",
  ]);
});

test("another trace starts afresh: nothing chosen, nothing folded", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView key="a" outline={TURN} reveal={revealing().reveal} />);
  await item(screen, "3").click();
  (item(screen, "1").element().querySelector("button") as HTMLElement).click();
  await expect.element(item(screen, "1")).toHaveAttribute("aria-expanded", "false");
  // A caller keys the view on the trace: another trace is another view.
  await screen.rerender(<TraceView key="b" outline={TURN} reveal={revealing().reveal} />);
  await expect.element(item(screen, "1")).toHaveAttribute("aria-expanded", "true");
  await expect.element(item(screen, "1")).toHaveAttribute("aria-selected", "true");
  await expect.element(screen.getByRole("region", { name: "span 1" })).toBeVisible();
});

test("on a phone, the bars give way to the names, and the details sit under the tree", async () => {
  await viewport(390, 844);
  const screen = await render(<TraceView outline={TURN} reveal={revealing().reveal} />);
  await expect.element(screen.getByRole("tree", { name: "Spans" })).toBeVisible();
  const tree = screen.getByRole("tree", { name: "Spans" }).element().getBoundingClientRect();
  const details = screen.getByRole("region", { name: "span 1" }).element().getBoundingClientRect();
  expect(details.top).toBeGreaterThan(tree.bottom - 1);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
  // The bar, aria-hidden, isn't drawn in so narrow a tree: its column is the name's.
  const bars = [...document.querySelectorAll('[role="treeitem"] > div[aria-hidden="true"]')].filter(
    (bar) => bar.className.includes("@xl:block"),
  );
  expect(bars.length).toBeGreaterThan(0);
  expect(bars.every((bar) => getComputedStyle(bar).display === "none")).toBe(true);
  // So a row's name has the room: "span 3" isn't cut to a stub.
  const name = [...document.querySelectorAll('[role="treeitem"] span.truncate')].find(
    (each) => each.textContent === "span 3",
  );
  expect(name && name.scrollWidth <= name.clientWidth).toBe(true);
});
