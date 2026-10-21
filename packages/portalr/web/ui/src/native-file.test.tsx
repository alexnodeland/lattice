import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { LONGEST_TITLE } from "./artifacts";
import { FileHolder, factsOf, fileSize, nativeFile, PageCompare, PageStrip } from "./native-file";
import { axeViolations } from "./test/axe";
import { FAILED, MANIFEST, NOW, PAGES, UNTIL } from "./test/native-file";

const renderer = nativeFile();

test("a native file shows its name, type, size, pages and outline", async () => {
  const screen = await render(renderer.render(MANIFEST));
  await expect.element(screen.getByText("launch-brief.docx")).toBeVisible();
  await expect.element(screen.getByText("Word document · 48 kB · 4 pages")).toBeVisible();
  const outline = screen.getByRole("region", { name: "Outline" });
  expect(
    outline
      .getByRole("listitem")
      .elements()
      .map((item) => item.textContent),
  ).toEqual(["Launch brief", "Who comes", "What to bring", "Who comes"]);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a manifest of any shape is shown as far as it goes", async () => {
  expect(factsOf({ content: "x", pages: -1, outline: 3 })).toEqual({
    name: "",
    type: "File",
    size: null,
    pages: null,
    outline: "",
  });
  expect(factsOf({ content: { media_type: "text/plain", size: 1 }, pages: 1 }).type).toBe(
    "text/plain",
  );
  const screen = await render(renderer.render({ pages: 1 }));
  await expect.element(screen.getByText("Unnamed file")).toBeVisible();
  await expect.element(screen.getByText("File · 1 page")).toBeVisible();
  await expect.element(screen.getByText("The app read no outline from this file.")).toBeVisible();
});

test.each([
  ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Workbook"],
  ["application/vnd.openxmlformats-officedocument.presentationml.presentation", "Presentation"],
  ["application/pdf", "PDF document"],
  ["image/vnd.dxf", "Drawing (DXF)"],
  ["image/vnd.dwg", "Drawing (DWG)"],
  ["image/vnd.adobe.photoshop", "Layered image"],
  ["image/svg+xml", "Vector image"],
  ["application/vnd.adobe.indesign-idml-package", "Page layout"],
  ["application/x-figcraft", "Design"],
  ["application/x-extension-fcstd", "3D model"],
  ["application/x-blender", "3D scene"],
])("a %s file is called a %s", (mediaType, type) => {
  expect(factsOf({ content: { media_type: mediaType } }).type).toBe(type);
});

test("its changes are its outline's, line by line, and its title is its name", () => {
  expect(renderer.text(MANIFEST)).toBe(MANIFEST.outline);
  expect(renderer.diff).toBe("lines");
  expect(renderer.title(MANIFEST)).toBe("launch-brief.docx");
  expect(renderer.title({ name: "  " })).toBeNull();
  const long = renderer.title({ name: `${"a".repeat(100)}.docx` }) ?? "";
  expect([...long]).toHaveLength(LONGEST_TITLE);
  expect(long.endsWith("…")).toBe(true);
});

test("a size reads in the unit that fits it", () => {
  expect(fileSize(0)).toBe("0 bytes");
  expect(fileSize(999)).toBe("999 bytes");
  expect(fileSize(1_234)).toBe("1.2 kB");
  expect(fileSize(48_213)).toBe("48 kB");
  expect(fileSize(999_950)).toBe("1 MB");
  expect(fileSize(25 * 1024 * 1024)).toBe("26 MB");
  expect(fileSize(3e15)).toBe("3000000 GB");
});

test("who has a file is said in words beside a shape, and announced", async () => {
  const screen = await render(
    <div>
      <FileHolder holder={{ kind: "free" }} />
      <FileHolder holder={{ kind: "you", until: UNTIL }} now={NOW} />
      <FileHolder holder={{ kind: "person", who: "bob@acme.test", until: UNTIL }} now={NOW} />
      <FileHolder holder={{ kind: "agent" }} />
      <FileHolder
        holder={{ kind: "person", who: "erin@acme.test", until: UNTIL }}
        now={new Date("2026-10-15T09:30:00Z")}
      />
    </div>,
  );
  const said = screen
    .getByRole("status")
    .elements()
    .map((status) => status.textContent);
  const today = new Date(UNTIL).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  expect(said.slice(0, 4)).toEqual([
    "Available to check out",
    `Checked out by you until ${today}`,
    `Checked out by bob@acme.test until ${today}`,
    "The agent is editing it",
  ]);
  expect(said[4]).toContain(String(new Date(UNTIL).getFullYear()));
  expect(screen.container.querySelector("time")?.getAttribute("datetime")).toBe(UNTIL);
});

test("pages are named by their number, and say when they are read or couldn't be", async () => {
  let more = 0;
  const screen = await render(
    <div>
      <PageStrip label="Pages" pages={PAGES} total={4} onMore={() => (more += 1)} />
      <PageStrip label="Pages of version 1" pages={FAILED} total={1} onMore={() => undefined} />
    </div>,
  );
  await expect.element(screen.getByRole("img", { name: "Page 1 of 4" })).toBeVisible();
  await expect.element(screen.getByText("Page 3 of 4, being read")).toBeInTheDocument();
  await expect.element(screen.getByText("This page couldn't be shown.")).toBeVisible();
  const buttons = screen.getByRole("button", { name: "Show more pages" });
  expect(buttons.elements()).toHaveLength(1);
  await buttons.click();
  expect(more).toBe(1);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("two versions' pages side by side, each row saying whether it changed", async () => {
  const [one, two] = PAGES as [{ page: number; src: string }, { page: number; src: string }];
  const screen = await render(
    <PageCompare
      label="Its pages beside the head's"
      before="Version 2"
      after="Proposed"
      pages={[
        { page: 1, before: one, after: one },
        { page: 2, before: one, after: { page: 2, src: two.src } },
        { page: 3, before: { page: 3, state: "reading" }, after: null },
        { page: 4, before: null, after: { page: 4, state: "failed" } },
      ]}
    />,
  );
  const rows = screen.getByRole("listitem").elements();
  expect(rows.map((row) => row.querySelector("p")?.textContent)).toEqual([
    "Page 1Unchanged",
    "Page 2Changed",
    "Page 3Gone",
    "Page 4New",
  ]);
  await expect.element(screen.getByRole("img", { name: "Page 2, Proposed" })).toBeVisible();
  await expect.element(screen.getByText("No page 3 here")).toBeVisible();
  await expect.element(screen.getByText("No page 4 here")).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
});
