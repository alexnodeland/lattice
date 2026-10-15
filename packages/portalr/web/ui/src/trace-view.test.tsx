import { type Outline, outline, type Trace } from "@portalr/client";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { viewport } from "./test/viewport";
import { duration, TraceView } from "./trace-view";

type Spans = Trace["spans"];

const span = (
  id: string,
  parent: string | null,
  start: number,
  end: number,
  attributes: Spans[number]["attributes"] = {},
  rest: Partial<Spans[number]> = {},
): Spans[number] => ({
  span_id: id,
  parent_id: parent,
  name: `span ${id}`,
  start_ns: start * 1_000_000,
  end_ns: end * 1_000_000,
  attributes,
  error: false,
  withheld: [],
  ...rest,
});

const made = (...spans: Spans): Outline => outline({ trace_id: "t".repeat(32), spans });

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
    { withheld: ["gen_ai.input.messages"] },
  ),
  span("3", "2", 20, 30, {
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": "publish",
  }),
  span("4", "1", 70, 90, {}, { error: true }),
);

const idle = { said: "hidden" as const, onAskToSee: vi.fn() };

test("a trace is a tree of its spans, deepest last, each named with what it is and how long it took", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} {...idle} />);
  const tree = screen.getByRole("tree", { name: "Spans" });
  await expect.element(tree).toBeVisible();
  const items = tree.getByRole("treeitem").elements();
  expect(items.map((item) => item.getAttribute("aria-label"))).toEqual([
    "span 1, Workflow, 100 ms",
    "span 2, Model call, 50 ms",
    "span 3, Tool, 10 ms",
    "span 4, Span, 20 ms, failed",
  ]);
  expect(items.map((item) => item.getAttribute("aria-level"))).toEqual(["1", "2", "3", "2"]);
  expect(items.map((item) => item.getAttribute("aria-expanded"))).toEqual([
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

test("the first span is chosen, and its details are shown; choosing another shows its own", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} {...idle} />);
  const details = screen.getByRole("region", { name: "span 1" });
  await expect.element(details.getByText("Workflow")).toBeVisible();
  await screen.getByRole("treeitem", { name: /^span 2,/ }).click();
  const model = screen.getByRole("region", { name: "span 2" });
  await expect.element(model.getByText("claude").first()).toBeVisible();
  await expect.element(model.getByText("120 in, 30 out")).toBeVisible();
  await expect.element(model.getByText("10 ms into the trace")).toBeVisible();
  await expect
    .element(screen.getByRole("treeitem", { name: /^span 2,/ }))
    .toHaveAttribute("aria-selected", "true");
  await screen.getByRole("treeitem", { name: /^span 4,/ }).click();
  await expect
    .element(screen.getByRole("region", { name: "span 4" }).getByText("Failed"))
    .toBeVisible();
  await screen.getByRole("treeitem", { name: /^span 3,/ }).click();
  await expect.element(screen.getByText("publish").first()).toBeVisible();
});

test("the arrow keys walk the tree and fold it", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} {...idle} />);
  const item = (n: number) => screen.getByRole("treeitem", { name: new RegExp(`^span ${n},`) });
  await item(1).click();
  await userEvent.keyboard("{ArrowDown}");
  await expect.element(item(2)).toHaveFocus();
  await expect.element(item(2)).toHaveAttribute("aria-selected", "true");
  await userEvent.keyboard("{ArrowDown}{ArrowDown}");
  await expect.element(item(4)).toHaveFocus();
  await userEvent.keyboard("{Home}");
  await expect.element(item(1)).toHaveFocus();
  await userEvent.keyboard("{End}");
  await expect.element(item(4)).toHaveFocus();
  // Left from a leaf goes to its parent; left from an open parent folds it.
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(item(1)).toHaveFocus();
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(item(1)).toHaveAttribute("aria-expanded", "false");
  await expect.element(item(2)).not.toBeInTheDocument();
  // Right opens it, and again goes to its first child.
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(item(2)).toBeVisible();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(item(2)).toHaveFocus();
  // Nothing before the first, nor after the last.
  await userEvent.keyboard("{Home}{ArrowUp}");
  await expect.element(item(1)).toHaveFocus();
});

test("only the rows in view are drawn, however long the trace", async () => {
  await viewport(1280, 900);
  const many = made(
    span("root", null, 0, 10_000),
    ...Array.from({ length: 2000 }, (_, at) => span(`s${at}`, "root", at, at + 1)),
  );
  const screen = await render(<TraceView outline={many} {...idle} />);
  await expect.element(screen.getByText("2001 spans in 10.00 s")).toBeVisible();
  const drawn = screen.getByRole("treeitem").elements().length;
  expect(drawn).toBeGreaterThan(5);
  expect(drawn).toBeLessThan(60);
});

test("what was said is kept back until a span asks for it, and then read once for the trace", async () => {
  await viewport(1280, 900);
  const ask = vi.fn();
  const screen = await render(<TraceView outline={TURN} said="hidden" onAskToSee={ask} />);
  await screen.getByRole("treeitem", { name: /^span 2,/ }).click();
  const said = screen.getByRole("region", { name: "What was said" });
  await expect.element(said.getByText(/kept out of the trace/)).toBeVisible();
  await said.getByRole("button", { name: "Show what was said" }).click();
  expect(ask).toHaveBeenCalledOnce();
  // The caller is reading it.
  await screen.rerender(<TraceView outline={TURN} said="reading" onAskToSee={ask} />);
  await expect.element(screen.getByRole("status")).toHaveTextContent("Reading…");
  // It came: the span's parts, labelled; another span still has its own to ask for.
  const spoken = made(
    span("1", null, 0, 100),
    span(
      "2",
      "1",
      10,
      60,
      {
        "gen_ai.input.messages": '[{"role":"user","content":"hi"}]',
        "gen_ai.output.messages": "hello",
      },
      {},
    ),
  );
  await screen.rerender(<TraceView outline={spoken} said="read" onAskToSee={ask} />);
  const after = screen.getByRole("region", { name: "What was said" });
  await expect.element(after.getByText("Prompt")).toBeVisible();
  await expect.element(after.getByText("Completion")).toBeVisible();
  await expect.element(after.getByText("hello")).toBeVisible();
});

test("what couldn't be read, and what wasn't recorded, are said", async () => {
  await viewport(1280, 900);
  const screen = await render(<TraceView outline={TURN} said="hidden" onAskToSee={vi.fn()} />);
  await screen.getByRole("treeitem", { name: /^span 2,/ }).click();
  await screen.getByRole("button", { name: "Show what was said" }).click();
  await screen.rerender(<TraceView outline={TURN} said="failed" onAskToSee={vi.fn()} />);
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("What was said couldn't be read.");
  await screen.rerender(<TraceView outline={TURN} said="read" onAskToSee={vi.fn()} />);
  await expect.element(screen.getByText("Nothing was recorded for this span.")).toBeVisible();
});

test("a span with no content has no section for it, and its attributes are listed in order", async () => {
  await viewport(1280, 900);
  const screen = await render(
    <TraceView
      outline={made(span("1", null, 0, 5, { b: "two", a: 1 }))}
      said="hidden"
      onAskToSee={vi.fn()}
    />,
  );
  await expect
    .element(screen.getByRole("region", { name: "What was said" }))
    .not.toBeInTheDocument();
  const attributes = screen.getByRole("region", { name: "Attributes" });
  expect(
    attributes
      .getByRole("term")
      .elements()
      .map((term) => term.textContent),
  ).toEqual(["a", "b"]);
});

test("a trace with no spans says so; durations are read as people read them", async () => {
  const screen = await render(<TraceView outline={made()} {...idle} />);
  await expect.element(screen.getByText("This trace has no spans.")).toBeVisible();
  expect([0.2, 12.4, 999, 1000, 2345].map(duration)).toEqual([
    "<1 ms",
    "12 ms",
    "999 ms",
    "1.00 s",
    "2.35 s",
  ]);
});

test("on a phone, the details sit under the tree and nothing scrolls the page sideways", async () => {
  await viewport(390, 844);
  const screen = await render(<TraceView outline={TURN} {...idle} />);
  await expect.element(screen.getByRole("tree", { name: "Spans" })).toBeVisible();
  const tree = screen.getByRole("tree", { name: "Spans" }).element().getBoundingClientRect();
  const details = screen.getByRole("region", { name: "span 1" }).element().getBoundingClientRect();
  expect(details.top).toBeGreaterThan(tree.bottom - 1);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
});
