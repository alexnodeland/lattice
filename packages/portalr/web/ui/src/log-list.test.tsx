import type { LogRecord } from "@portalr/client";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { type LineReveal, LogList } from "./log-list";
import { viewport } from "./test/viewport";
import type { Standing } from "./trace-view";

const record = (n: number, rest: Partial<LogRecord> = {}): LogRecord => ({
  id: `${1000 - n}-${String(n).padStart(16, "0")}`,
  time_ns: (1_792_113_515_000 - n) * 1_000_000,
  level: "info",
  service: "docplan",
  thread: null,
  run: null,
  length: 10 + n,
  labels: { service_name: "docplan", tenant_id: "acme" },
  withheld: [],
  line: null,
  ...rest,
});

const FEW = [
  record(1, { level: "error", thread: "thr_1", run: "run_9", withheld: ["email", "extra_thing"] }),
  record(2),
  record(3, { level: null, service: null }),
];

function revealing(standing: Record<string, Standing> = {}, lines: Record<string, string> = {}) {
  const ask = vi.fn();
  const reveal: LineReveal = {
    standing: (id) => standing[id] ?? "hidden",
    line: (id) => lines[id] ?? null,
    ask,
  };
  return { reveal, ask };
}

const option = (screen: Awaited<ReturnType<typeof render>>, n: number) =>
  screen.getByRole("option", { name: new RegExp(`${10 + n} characters$`) });

test("records are a list, each named for when, how bad, whose and how long, with its place in the list", async () => {
  await viewport(1280, 900);
  const screen = await render(<LogList records={FEW} complete reveal={revealing().reveal} />);
  const list = screen.getByRole("listbox", { name: "3 records, newest first" });
  await expect.element(list).toBeVisible();
  const items = list.getByRole("option").elements();
  expect(items.map((each) => each.getAttribute("aria-posinset"))).toEqual(["1", "2", "3"]);
  expect(items.every((each) => each.getAttribute("aria-setsize") === "3")).toBe(true);
  expect(items[0]?.getAttribute("aria-label")).toMatch(
    /, error, docplan, thread thr_1, run run_9, 11 characters$/,
  );
  expect(items[2]?.getAttribute("aria-label")).toMatch(/^[^,]+, 13 characters$/);
  expect(items[0]?.getAttribute("aria-selected")).toBe("true");
});

test("a list that isn't all of them says so, and an empty window says so", async () => {
  const screen = await render(
    <LogList records={FEW} complete={false} reveal={revealing().reveal} />,
  );
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(
      "These are the newest: there may be more. A shorter window, or a thread or a run, finds the rest.",
    );
  const empty = await render(<LogList records={[]} complete reveal={revealing().reveal} />);
  await expect.element(empty.getByText("No log records in this window.")).toBeVisible();
});

test("the chosen record's details name its labels and what was kept out, and never its line", async () => {
  await viewport(1280, 900);
  const screen = await render(<LogList records={FEW} complete reveal={revealing().reveal} />);
  const details = screen.getByRole("region", { name: /^\d+\/\d+\/\d+, / });
  await expect.element(details.getByText("thr_1")).toBeVisible();
  await expect.element(details.getByText("11 characters")).toBeVisible();
  await expect.element(details.getByText("email, extra_thing")).toBeVisible();
  await expect.element(details.getByText(/kept out of the list/)).toBeVisible();
  await option(screen, 2).click();
  await expect.element(option(screen, 2)).toHaveAttribute("aria-selected", "true");
  await expect.element(screen.getByText("thr_1")).not.toBeInTheDocument();
});

test("the arrow, page, home and end keys walk the list", async () => {
  await viewport(1280, 900);
  const many = Array.from({ length: 40 }, (_, at) => record(at + 1));
  const screen = await render(<LogList records={many} complete reveal={revealing().reveal} />);
  await option(screen, 1).click();
  await userEvent.keyboard("{ArrowDown}");
  await expect.element(option(screen, 2)).toHaveFocus();
  await userEvent.keyboard("{PageDown}");
  await expect.element(option(screen, 12)).toHaveFocus();
  await userEvent.keyboard("{ArrowUp}{ArrowUp}");
  await expect.element(option(screen, 10)).toHaveFocus();
  await userEvent.keyboard("{End}");
  await expect.element(option(screen, 40)).toHaveFocus();
  await userEvent.keyboard("{PageDown}{ArrowDown}");
  await expect.element(option(screen, 40)).toHaveFocus();
  await userEvent.keyboard("{Home}");
  await expect.element(option(screen, 1)).toHaveFocus();
  await userEvent.keyboard("{PageUp}{ArrowUp}");
  await expect.element(option(screen, 1)).toHaveFocus();
});

test("a thousand records draw a screenful; the list keeps a tab stop when the chosen one is scrolled away; End draws the last", async () => {
  await viewport(1280, 900);
  const thousand = Array.from({ length: 1000 }, (_, at) => record(at + 1));
  const screen = await render(<LogList records={thousand} complete reveal={revealing().reveal} />);
  const list = screen.getByRole("listbox");
  const drawn = screen.getByRole("option").elements().length;
  expect(drawn).toBeGreaterThan(5);
  expect(drawn).toBeLessThan(60);
  list.element().scrollTop = 20_000;
  await expect
    .poll(() =>
      screen
        .getByRole("option")
        .elements()
        .some((row) => row.tabIndex === 0),
    )
    .toBe(false);
  expect((list.element() as HTMLElement).tabIndex).toBe(0);
  (list.element() as HTMLElement).focus();
  await expect.element(option(screen, 1)).toHaveFocus();
  await userEvent.keyboard("{End}");
  await expect.element(option(screen, 1000)).toHaveFocus();
  expect(screen.getByRole("option").elements().length).toBeLessThan(60);
});

test("a line is asked for by its record, and is read, being read, or couldn't be", async () => {
  await viewport(1280, 900);
  const first = FEW[0] as LogRecord;
  const { reveal, ask } = revealing();
  const screen = await render(<LogList records={FEW} complete reveal={reveal} />);
  await screen.getByRole("button", { name: "Show this line" }).click();
  expect(ask).toHaveBeenCalledExactlyOnceWith(first.id);
  await screen.unmount();
  for (const [standing, said] of [
    ["reading", "Reading…"],
    ["failed", "The line couldn't be read."],
    ["read", "The read returned no such record."],
  ] as const) {
    const other = revealing({ [first.id]: standing });
    const again = await render(<LogList records={FEW} complete reveal={other.reveal} />);
    await expect.element(again.getByText(said)).toBeVisible();
    await again.unmount();
  }
  const esc = "\u001b";
  const read = revealing(
    { [first.id]: "read" },
    { [first.id]: `${esc}[31mboom${esc}[0m ${esc}[2J<b>x</b>` },
  );
  const shown = await render(<LogList records={FEW} complete reveal={read.reveal} />);
  const line = shown.getByRole("region", { name: "Line" });
  await expect.element(line).toBeVisible();
  expect(line.element().querySelector("pre")?.textContent).toBe("boom <b>x</b>");
  const red = line.element().querySelector("pre span") as HTMLElement;
  expect(red.style.color).toBe("var(--ansi-1)");
  expect(line.element().querySelector("b")).toBeNull();
  // Another record still has its own line to ask for.
  await option(shown, 2).click();
  await expect.element(shown.getByRole("button", { name: "Show this line" })).toBeVisible();
});

test("on a phone, the details sit under the list and nothing scrolls the page sideways", async () => {
  await viewport(390, 844);
  const screen = await render(<LogList records={FEW} complete reveal={revealing().reveal} />);
  const list = screen.getByRole("listbox").element().getBoundingClientRect();
  const details = screen
    .getByRole("region", { name: /^\d+\/\d+\/\d+, / })
    .element()
    .getBoundingClientRect();
  expect(details.top).toBeGreaterThan(list.bottom - 1);
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
  // A row's two lines fit its width: neither overflows it.
  for (const row of screen.getByRole("option").elements()) {
    expect(row.scrollWidth).toBeLessThanOrEqual(row.clientWidth);
  }
});
