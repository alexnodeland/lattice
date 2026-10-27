import { describe, expect, onTestFinished, test } from "vitest";
import { commands, page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import UI_SCHEMA from "../../../../artifactr/schemas/artifactr_ui.v1.json";
import { type Dashboard, MAX_TABLE_ROWS, type Panel, type TablePanel } from "./artifactr-ui";
import { MAX_SERIES } from "./chart-theme";
import { PANELS, type PanelProps } from "./dashboard-panels";
import { DashboardView, readDashboard } from "./dashboard-view";
import { IntegrationsContext } from "./integrations";
import { token } from "./test/colours";
import { SUPPORT } from "./test/dashboards";

const only = (...panels: Panel[]): Dashboard => ({ title: "", as_of: "", panels });

describe("reading a dashboard", () => {
  test("holds a chart's series and a table's rows to the package's schema", () => {
    const panels = UI_SCHEMA.$defs;
    expect(panels.ChartPanel.properties.series.maxItems).toBe(MAX_SERIES);
    expect(panels.TablePanel.properties.rows.maxItems).toBe(MAX_TABLE_ROWS);
  });

  test("every panel it knows is read as it is", () => {
    expect(readDashboard(SUPPORT)).toEqual({ dashboard: SUPPORT, unshown: 0 });
  });

  test("a panel it can't show is left out, and counted", () => {
    const read = readDashboard({
      title: 7,
      panels: [
        { type: "stat", label: "Open", value: 1 },
        { type: "stat", label: "Open", value: true },
        { type: "stat", label: "Open", value: 1, unit: 3 },
        { type: "stat", label: "Open", value: 1, change: "up" },
        { type: "bar", label: "x", index: { key: "d" }, series: [], rows: [] },
        {
          type: "line",
          label: "x",
          index: { key: "d", name: "D" },
          series: [],
          rows: [{ d: true }],
        },
        { type: "donut", label: "x", parts: [{ key: "a", name: "a", value: "1" }] },
        { type: "table", label: "x", columns: "a", rows: [] },
        { type: "table", label: "x", columns: [], rows: [] },
        { type: "table", label: "x", columns: [{ key: "a", name: "A" }], rows: [{ a: {} }] },
        { type: "donut", label: "x", parts: [] },
        { type: "bar", label: "x", index: { key: "d", name: "D" }, series: [], rows: [] },
        { type: "text", text: 1 },
        { type: "form" },
        { type: "map" },
        "stat",
      ],
    });
    expect(read).toEqual({
      dashboard: { title: "", as_of: "", panels: [{ type: "stat", label: "Open", value: 1 }] },
      unshown: 15,
    });
  });

  test.each([null, [], { panels: "none" }])("data without panels, %j, are no dashboard", (data) => {
    expect(readDashboard(data)).toBeNull();
  });
});

test("when its figures were true is said first, in UTC; a moment it can't read, as it came", async () => {
  const screen = await render(<DashboardView dashboard={only()} />);
  await expect.element(screen.getByRole("paragraph")).not.toBeInTheDocument();
  await screen.rerender(<DashboardView dashboard={{ ...only(), as_of: SUPPORT.as_of }} />);
  const time = screen.getByText("17 Oct 2026, 09:30 UTC");
  await expect.element(time).toHaveAttribute("datetime", "2026-10-17T09:30:00Z");
  await screen.rerender(<DashboardView dashboard={{ ...only(), as_of: "this morning" }} />);
  await expect.element(screen.getByText("Figures as of this morning")).toBeVisible();
  // Only RFC 3339 is a moment here: what a browser would guess at is shown as it came.
  await screen.rerender(<DashboardView dashboard={{ ...only(), as_of: "2026-10-17 09:30" }} />);
  await expect.element(screen.getByText("Figures as of 2026-10-17 09:30")).toBeVisible();
});

test("figures sit side by side, each in its unit, and how it moved said in words", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  const open = screen.getByRole("article", { name: "Open tickets" });
  await expect.element(open).toHaveTextContent("Open tickets42Down 6");
  await expect
    .element(screen.getByRole("article", { name: "First reply" }))
    .toHaveTextContent("First reply1.8 hUp 0.3 h");
  await expect
    .element(screen.getByRole("article", { name: "Solved on first reply" }))
    .toHaveTextContent("Solved on first reply64%No change");
  await expect
    .element(screen.getByRole("article", { name: "On call" }))
    .toHaveTextContent("On callBob");
  const tops = ["Open tickets", "On call"].map(
    (name) => screen.getByRole("article", { name }).element().getBoundingClientRect().top,
  );
  expect(tops[0]).toBe(tops[1]);
});

test("a percentage's change is in points", async () => {
  const screen = await render(
    <DashboardView
      dashboard={only({ type: "stat", label: "Rate", value: 5, unit: "%", change: -2 })}
    />,
  );
  await expect
    .element(screen.getByRole("article", { name: "Rate" }))
    .toHaveTextContent("Rate5%Down 2 points");
});

test("each chart is the kit's, named by its title, its figures under Show the figures", async () => {
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  for (const name of [
    "Tickets by channel",
    "Median first reply, hours",
    "Open tickets by priority",
  ]) {
    const figure = screen.getByRole("figure", { name });
    await expect.element(figure).toBeVisible();
    await expect.element(figure.getByText("Show the figures")).toBeVisible();
  }
  // The donut's parts past its inks are one, "Other".
  const donut = screen.getByRole("figure", { name: "Open tickets by priority" });
  await expect.element(donut.getByText("Other", { exact: true }).first()).toBeVisible();
});

test("a table's first column names each row; a cell with nothing in it is a dash", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  const table = screen.getByRole("table", { name: "Longest open" });
  await expect
    .element(table.getByRole("row", { name: "T-1103" }))
    .toHaveTextContent("T-1103Invoice shows the wrong VAT––");
});

test("a table holds 500 rows at most, says how many it left out, and pages through 50 at a time", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const rows = Array.from({ length: 502 }, (_, at) => ({ n: at + 1 }));
  const screen = await render(
    <DashboardView
      dashboard={only({ type: "table", label: "Many", columns: [{ key: "n", name: "N" }], rows })}
    />,
  );
  await expect.element(screen.getByText("The first 500 rows of 502.")).toBeVisible();
  await expect.element(screen.getByText("Rows 1 to 50 of 500.")).toBeVisible();
  expect(screen.getByRole("table", { name: "Many" }).getByRole("row").elements()).toHaveLength(51);
  await expect
    .element(screen.getByRole("group", { name: "Pages of Many" }))
    .toHaveTextContent("Pages of ManyPrevious rowsNext rows");
  await screen.getByRole("button", { name: "Next rows" }).click();
  await expect.element(screen.getByText("Rows 51 to 100 of 500.")).toBeVisible();
  await expect.element(screen.getByRole("row", { name: "51" })).toBeVisible();
});

test("a table keeps its page as the dashboard is drawn again, as a stream's events draw it", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const rows = Array.from({ length: 120 }, (_, at) => ({ n: at + 1 }));
  const dashboard = only({
    type: "table",
    label: "Many",
    columns: [{ key: "n", name: "N" }],
    rows,
  });
  const screen = await render(<DashboardView dashboard={dashboard} />);
  await screen.getByRole("button", { name: "Next rows" }).click();
  await expect.element(screen.getByText("Rows 51 to 100 of 120.")).toBeVisible();
  await screen.rerender(<DashboardView dashboard={dashboard} unshown={1} />);
  await expect.element(screen.getByText("One panel can't be shown here.")).toBeVisible();
  await expect.element(screen.getByText("Rows 51 to 100 of 120.")).toBeVisible();
});

test("a pager's button keeps the focus on the first and the last page, where it can't be pressed", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const rows = Array.from({ length: 60 }, (_, at) => ({ n: at + 1 }));
  const screen = await render(
    <DashboardView
      dashboard={only({ type: "table", label: "Many", columns: [{ key: "n", name: "N" }], rows })}
    />,
  );
  const next = screen.getByRole("button", { name: "Next rows" });
  await next.click();
  await expect.element(screen.getByText("Rows 51 to 60 of 60.")).toBeVisible();
  await expect.element(next).toHaveAttribute("aria-disabled", "true");
  expect(document.activeElement).toBe(next.element());
});

test("a table without rows says so", async () => {
  const screen = await render(
    <DashboardView
      dashboard={only({
        type: "table",
        label: "Empty",
        columns: [{ key: "n", name: "N" }],
        rows: [],
      })}
    />,
  );
  await expect.element(screen.getByText("No rows")).toBeVisible();
});

test("text is Markdown, with no HTML", async () => {
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  const words = screen.getByText("up", { exact: true });
  await expect.element(words).toHaveClass("font-semibold");
  const card = words.element().closest("[class*='--card-shadow']") as Element;
  expect(card.textContent).toContain("<b>Raw HTML</b>");
  expect(card.querySelector("b")).toBeNull();
});

test("a table's yes or no is said in words", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  await expect
    .element(
      screen.getByRole("table", { name: "Longest open" }).getByRole("row", { name: "T-1120" }),
    )
    .toHaveTextContent("T-1120Refund for a duplicate charge4Yes");
  await expect
    .element(screen.getByRole("row", { name: "T-1042" }))
    .toHaveTextContent("T-1042Export stops at 10,000 rows12–");
});

test("a form panel is the caller's to show, by its id; without a caller, it says it can't be", async () => {
  const screen = await render(
    <DashboardView
      dashboard={only({ type: "form", form_id: "form_ack" })}
      form={(id) => <p>Form {id}</p>}
    />,
  );
  await expect.element(screen.getByText("Form form_ack")).toBeVisible();
  await screen.rerender(<DashboardView dashboard={only({ type: "form", form_id: "form_ack" })} />);
  await expect.element(screen.getByText("form_ack")).toHaveProperty("tagName", "CODE");
  await expect.element(screen.getByText(/which can't be shown here/)).toBeVisible();
});

test("the panels it couldn't show are counted beneath", async () => {
  const screen = await render(<DashboardView dashboard={only()} unshown={1} />);
  await expect.element(screen.getByText("One panel can't be shown here.")).toBeVisible();
  await screen.rerender(<DashboardView dashboard={only()} unshown={3} />);
  await expect.element(screen.getByText("3 panels can't be shown here.")).toBeVisible();
});

test("its charts take the colour-blind inks, and their patterns under forced colours", async () => {
  onTestFinished(() => commands.forcedColors(false));
  onTestFinished(() => {
    delete document.documentElement.dataset.cvd;
  });
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  const figure = screen.getByRole("figure", { name: "Tickets by channel" }).element();
  const bar = () => figure.querySelector(".recharts-bar-rectangle path") as Element;
  await expect.poll(() => bar()).toBeTruthy();
  const hatch = () => Number(getComputedStyle(figure).getPropertyValue("--chart-hatch"));
  expect(getComputedStyle(bar()).fill).toBe(token("chart-1"));
  expect(hatch()).toBe(0);
  const plain = token("chart-1");
  document.documentElement.dataset.cvd = "";
  expect(token("chart-1")).not.toBe(plain);
  expect(getComputedStyle(bar()).fill).toBe(token("chart-1"));
  expect(hatch()).toBeGreaterThan(0);
  delete document.documentElement.dataset.cvd;
  await commands.forcedColors(true);
  expect(hatch()).toBeGreaterThan(0);
});

test("a table's column named for what an object inherits is empty, not the inherited", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <DashboardView
      dashboard={only({
        type: "table",
        label: "Odd",
        columns: [
          { key: "n", name: "N" },
          { key: "constructor", name: "Made by" },
        ],
        rows: [{ n: "one" }],
      })}
    />,
  );
  await expect
    .element(screen.getByRole("table", { name: "Odd" }).getByRole("row", { name: "one" }))
    .toHaveTextContent("one–");
});

test("a panel is drawn by the renderer registered for its type, so one can be put in another's place", async () => {
  function Rows({ panel }: PanelProps<TablePanel>) {
    return <p>{`${panel.label}: ${panel.rows.length} rows, drawn another way`}</p>;
  }
  const screen = await render(
    <DashboardView dashboard={SUPPORT} panels={{ ...PANELS, table: Rows }} />,
  );
  await expect.element(screen.getByText("Longest open: 4 rows, drawn another way")).toBeVisible();
  await expect.element(screen.getByRole("table")).not.toBeInTheDocument();
  // Every other type is still the kit's.
  await expect.element(screen.getByRole("article", { name: "Open tickets" })).toBeVisible();
  await expect.element(screen.getByRole("figure", { name: "Tickets by channel" })).toBeVisible();
});

test("a renderer of the page's own is given the chart theme's colours, resolved", async () => {
  function Inks({ panel, tokens }: PanelProps<Extract<Panel, { type: "bar" | "line" | "donut" }>>) {
    return <p>{`${panel.label}: ${tokens === null ? "unread" : tokens.colours["chart-1"]}`}</p>;
  }
  const screen = await render(
    <DashboardView dashboard={SUPPORT} panels={{ ...PANELS, bar: Inks }} />,
  );
  await expect.element(screen.getByText(`Tickets by channel: ${token("chart-1")}`)).toBeVisible();
});

test("a chart and a table are each headed, so a reader moving by headings finds both", async () => {
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  for (const name of ["Tickets by channel", "Open tickets by priority", "Longest open"]) {
    await expect.element(screen.getByRole("heading", { level: 2, name })).toBeVisible();
  }
});

describe("a table panel, once the dashboards add-on is in", () => {
  const TICKETS = SUPPORT.panels.find((panel) => panel.type === "table") as TablePanel;
  const table = async () => {
    await page.viewport(1000, 800);
    onTestFinished(() => page.viewport(414, 896));
    const screen = await render(<DashboardView dashboard={only(TICKETS)} />);
    await expect
      .element(screen.getByRole("searchbox", { name: "Filter Longest open" }))
      .toBeVisible();
    return screen;
  };
  const firstColumn = (screen: Awaited<ReturnType<typeof table>>) =>
    screen
      .getByRole("table", { name: "Longest open" })
      .getByRole("rowheader")
      .elements()
      .map((cell) => cell.textContent);

  test("sorts by a column's heading, which says how it is sorted, numbers by value and nothing last", async () => {
    const screen = await table();
    const days = screen.getByRole("columnheader", { name: /Days open/ });
    await expect.element(days).not.toHaveAttribute("aria-sort");
    await days.getByRole("button").click();
    await expect.element(days).toHaveAttribute("aria-sort", "ascending");
    expect(firstColumn(screen)).toEqual(["T-1120", "T-1077", "T-1042", "T-1103"]);
    await days.getByRole("button").click();
    await expect.element(days).toHaveAttribute("aria-sort", "descending");
    expect(firstColumn(screen)).toEqual(["T-1042", "T-1077", "T-1120", "T-1103"]);
  });

  test("filters by the words a cell reads as, and says how many rows hold them", async () => {
    const screen = await table();
    await screen.getByRole("searchbox", { name: "Filter Longest open" }).fill("yes");
    await expect.element(screen.getByText("Rows 1 to 1 of 1.")).toBeVisible();
    expect(firstColumn(screen)).toEqual(["T-1120"]);
    await screen.getByRole("searchbox", { name: "Filter Longest open" }).fill("nothing like it");
    await expect.element(screen.getByText("No rows hold those words.")).toBeVisible();
    await expect.element(screen.getByRole("table")).not.toBeInTheDocument();
  });

  test("sorts by one column at a time, even with Shift held", async () => {
    const screen = await table();
    const days = screen.getByRole("columnheader", { name: /Days open/ });
    const ticket = screen.getByRole("columnheader", { name: /Ticket/ });
    await days.getByRole("button").click();
    await userEvent.keyboard("{Shift>}");
    await ticket.getByRole("button").click();
    await userEvent.keyboard("{/Shift}");
    await expect.element(ticket).toHaveAttribute("aria-sort", "ascending");
    await expect.element(days).not.toHaveAttribute("aria-sort");
  });

  test("is sorted by the keyboard: Tab to a heading, Enter and Space", async () => {
    const screen = await table();
    const ticket = screen.getByRole("columnheader", { name: /Ticket/ });
    ticket.getByRole("button").element().focus();
    await userEvent.keyboard("{Enter}");
    await expect.element(ticket).toHaveAttribute("aria-sort", "ascending");
    await userEvent.keyboard(" ");
    await expect.element(ticket).toHaveAttribute("aria-sort", "descending");
    const button = ticket.getByRole("button").element();
    expect(button.matches(":focus-visible")).toBe(true);
    expect(getComputedStyle(button).outlineColor).toBe(token("focus"));
  });

  test("a column's heading is a target 24px tall or more, the kit's small ghost button", async () => {
    const screen = await table();
    const button = screen.getByRole("columnheader", { name: /Ticket/ }).getByRole("button");
    expect(button.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(24);
    expect(getComputedStyle(button.element()).backgroundColor).toBe("rgba(0, 0, 0, 0)");
  });
});

test("with dashboards off, a chart isn't drawn, its figures from the panel are open, and a table is plain", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <IntegrationsContext value={(key) => key !== "ui:dashboards"}>
      <DashboardView dashboard={SUPPORT} />
    </IntegrationsContext>,
  );
  const bars = screen.getByRole("figure", { name: "Tickets by channel" });
  await expect
    .element(
      bars.getByText(
        "Not available in this workspace: dashboards are off. This chart isn't drawn: its figures are below.",
      ),
    )
    .toBeVisible();
  expect(bars.element().querySelector("svg.recharts-surface")).toBeNull();
  await expect
    .element(
      bars.getByRole("table", { name: "Tickets by channel" }).getByRole("row", { name: "Sep 22" }),
    )
    .toHaveTextContent("Sep 2230229");
  const donut = screen.getByRole("figure", { name: "Open tickets by priority" });
  await expect
    .element(donut.getByRole("table").getByRole("row", { name: "Low" }))
    .toHaveTextContent("Low1843%");
  await expect.element(screen.getByRole("searchbox")).not.toBeInTheDocument();
  await expect.element(screen.getByRole("table", { name: "Longest open" })).toBeVisible();
});

test("a chart's figures are the panel's, under Show the figures, whatever draws it", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  const line = screen.getByRole("figure", { name: "Median first reply, hours" });
  await expect.element(line.getByText("Show the figures")).toBeVisible();
  await line.getByText("Show the figures").click();
  await expect
    .element(
      line
        .getByRole("table", { name: "Median first reply, hours" })
        .getByRole("row", { name: "Oct 6" }),
    )
    .toHaveTextContent("Oct 61.5");
});
