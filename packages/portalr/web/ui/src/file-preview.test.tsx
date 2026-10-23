import { useState } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import type { PageShown } from "./file-pages";
import { columnName, PageViewer, SHOWN_ROWS, SheetTable, sheetsOf } from "./file-preview";
import { axeViolations } from "./test/axe";
import { PAGES } from "./test/native-file";

/** A viewer over four pages, which shows the drawn ones and reads the rest. */
function Viewer({ dir }: { dir?: "rtl" }) {
  const [page, setPage] = useState(1);
  const shown: PageShown = PAGES.find((each) => each.page === page) ?? {
    page,
    state: page === 4 ? "failed" : "reading",
  };
  return (
    <div dir={dir}>
      <PageViewer label="launch-brief.docx, version 3" shown={shown} total={4} onPage={setPage} />
    </div>
  );
}

test("a page is shown one at a time, paged through by its buttons", async () => {
  const screen = await render(<Viewer />);
  const viewer = screen.getByRole("region", { name: "launch-brief.docx, version 3" });
  await expect.element(viewer.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  await expect.element(viewer.getByRole("button", { name: "Previous page" })).toBeDisabled();
  await viewer.getByRole("button", { name: "Next page" }).click();
  await expect.element(viewer.getByRole("img", { name: "Page 2 of 4" })).toBeVisible();
  await expect.element(viewer.getByText("Page 2 of 4", { exact: true })).toBeVisible();
  await viewer.getByRole("button", { name: "Next page" }).click();
  // Being read: a placeholder of a page's shape, and no image yet.
  expect(viewer.getByRole("img").elements()).toHaveLength(0);
  await viewer.getByRole("button", { name: "Next page" }).click();
  await expect.element(viewer.getByText(/^This page couldn't be shown\./)).toBeVisible();
  await expect.element(viewer.getByRole("button", { name: "Next page" })).toBeDisabled();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("the keys page through it", async () => {
  const screen = await render(<Viewer />);
  const page = screen.getByRole("region", { name: /: Page / });
  (page.element() as HTMLElement).focus();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByRole("img", { name: "Page 2 of 4" })).toBeVisible();
  await userEvent.keyboard("{End}");
  await expect.element(screen.getByText("Page 4 of 4", { exact: true })).toBeVisible();
  await userEvent.keyboard("{PageUp}");
  await expect.element(screen.getByText("Page 3 of 4", { exact: true })).toBeVisible();
  await userEvent.keyboard("{Home}");
  await expect.element(screen.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(screen.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  await userEvent.keyboard("{PageDown}");
  await expect.element(screen.getByRole("img", { name: "Page 2 of 4" })).toBeVisible();
  // Another key is left alone.
  await userEvent.keyboard("a");
  await expect.element(screen.getByRole("img", { name: "Page 2 of 4" })).toBeVisible();
});

test("in a page read right to left, the arrow keys go the other way", async () => {
  const rtl = await render(<Viewer dir="rtl" />);
  (rtl.getByRole("region", { name: /: Page / }).element() as HTMLElement).focus();
  await userEvent.keyboard("{ArrowLeft}");
  await expect.element(rtl.getByRole("img", { name: "Page 2 of 4" })).toBeVisible();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(rtl.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
});

test("a page is seen at its own size, pressed, and fitted again", async () => {
  const screen = await render(<Viewer />);
  const actual = screen.getByRole("button", { name: "Actual size" });
  await expect.element(actual).toHaveAttribute("aria-pressed", "false");
  await actual.click();
  await expect.element(actual).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("img").element().className).toContain("max-w-none");
  await actual.click();
  await expect.element(actual).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("img").element().className).not.toContain("max-w-none");
});

test("a workbook's text is read into its sheets, the outline saying which line names one", () => {
  const text = "Costs\nItem\tCost\n\nPaper\t12\n\nPlan\nWeek\tGoal";
  expect(sheetsOf(text, ["Costs", "Plan"])).toEqual([
    { name: "Costs", rows: [["Item", "Cost"], [""], ["Paper", "12"]] },
    { name: "Plan", rows: [["Week", "Goal"]] },
  ]);
  // Without the outline, every empty line parts sheets.
  expect(sheetsOf("A\n1\n\nB\n2").map((sheet) => sheet.name)).toEqual(["A", "B"]);
  expect(sheetsOf("Empty")).toEqual([{ name: "Empty", rows: [] }]);
  expect(sheetsOf("Last\n1\n")).toEqual([{ name: "Last", rows: [["1"], [""]] }]);
});

test("columns are lettered as a spreadsheet letters them", () => {
  expect([0, 1, 25, 26, 27, 51, 52, 701, 702].map(columnName)).toEqual([
    "A",
    "B",
    "Z",
    "AA",
    "AB",
    "AZ",
    "BA",
    "ZZ",
    "AAA",
  ]);
});

test("a sheet is a table named by it, its columns lettered and its rows numbered", async () => {
  const screen = await render(
    <SheetTable
      sheet={{
        name: "Costs",
        rows: [
          ["Item", "Cost"],
          ["Paper", "12", "spare"],
        ],
      }}
    />,
  );
  const table = screen.getByRole("table", { name: "Costs" });
  await expect.element(table.getByRole("columnheader", { name: "C" })).toBeVisible();
  await expect.element(table.getByRole("rowheader", { name: "2" })).toBeVisible();
  await expect.element(table.getByRole("cell", { name: "spare" })).toBeVisible();
  expect(table.getByRole("row").elements()).toHaveLength(3);
  expect(screen.container.textContent).not.toContain("The first");
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a long sheet shows its first rows, and says so", async () => {
  const rows = Array.from({ length: SHOWN_ROWS + 5 }, (_, row) => [`Row ${row + 1}`]);
  const screen = await render(<SheetTable sheet={{ name: "Long", rows }} />);
  expect(screen.getByRole("row").elements()).toHaveLength(SHOWN_ROWS + 1);
  await expect
    .element(
      screen.getByText(`The first ${SHOWN_ROWS} of ${SHOWN_ROWS + 5} rows.`, { exact: false }),
    )
    .toBeVisible();
});

test("a key with a modifier is the browser's, and at its own size the arrows scroll, not page", async () => {
  const screen = await render(<Viewer />);
  const box = screen.getByRole("region", { name: /: Page / });
  (box.element() as HTMLElement).focus();
  for (const key of [
    "{Alt>}{ArrowRight}{/Alt}",
    "{Control>}{ArrowRight}{/Control}",
    "{Meta>}{ArrowRight}{/Meta}",
    "{Shift>}{ArrowRight}{/Shift}",
  ]) {
    await userEvent.keyboard(key);
  }
  await expect.element(screen.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  await screen.getByRole("button", { name: "Actual size" }).click();
  (box.element() as HTMLElement).focus();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  await userEvent.keyboard("{PageDown}");
  await expect.element(screen.getByRole("img", { name: "Page 2 of 4" })).toBeVisible();
});

test("a wide sheet shows its first columns, as wide as the rows shown, and says so", async () => {
  const wide = Array.from({ length: 60 }, (_, at) => `c${at}`);
  const screen = await render(
    <SheetTable
      sheet={{ name: "Wide", rows: [wide, ...Array.from({ length: 300 }, () => ["x"])] }}
    />,
  );
  const table = screen.getByRole("table", { name: "Wide" });
  // The corner names the row numbers' column, for a screen reader.
  await expect.element(table.getByRole("columnheader", { name: "Row" })).toBeInTheDocument();
  expect(table.getByRole("columnheader").elements()).toHaveLength(51);
  await expect
    .element(screen.getByText(/^The first 200 of 301 rows\. The first 50 of 60 columns\./))
    .toBeVisible();
  // Only the rows shown set the width: a wide row past them adds no column.
  const late = await render(
    <SheetTable
      sheet={{ name: "Late", rows: [...Array.from({ length: 200 }, () => ["x"]), wide] }}
    />,
  );
  expect(
    late.getByRole("table", { name: "Late" }).getByRole("columnheader").elements(),
  ).toHaveLength(2);
});

test("the text has no escapes: a tab or a line break in a cell reads as two cells or two rows", () => {
  // As the app writes a sheet: a tab between cells, a line a row, whatever a cell holds.
  expect(sheetsOf("Notes\nsee\tbelow\nsecond line", ["Notes"])).toEqual([
    { name: "Notes", rows: [["see", "below"], ["second line"]] },
  ]);
});
