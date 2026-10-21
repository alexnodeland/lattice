import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { plainName, type UploadItem, UploadList } from "./upload-list";

const ITEMS: UploadItem[] = [
  { id: "1", name: "brief.docx", size: 48_000, state: "done", said: "Uploaded brief.docx." },
  { id: "2", name: "plan.xlsx", size: 20_000, state: "sending", sent: 5_000 },
  { id: "3", name: "deck.pptx", size: 1_000, state: "waiting" },
  {
    id: "4",
    name: "scan.pdf",
    size: 2_000,
    state: "failed",
    said: "PdfCraft couldn't finish reading scan.pdf. Try again in a moment.",
    tone: "error",
    again: true,
  },
  { id: "5", name: "notes.txt", size: 10, state: "failed", said: "Not taken.", tone: "error" },
];

test("each file says where it is, and its controls name it", async () => {
  const done: string[] = [];
  const screen = await render(
    <UploadList
      items={ITEMS}
      onStop={(id) => done.push(`stop ${id}`)}
      onRemove={(id) => done.push(`remove ${id}`)}
      onRetry={(id) => done.push(`retry ${id}`)}
    />,
  );
  const progress = screen.getByRole("progressbar", { name: "Uploading plan.xlsx" });
  await expect.element(progress).toHaveAttribute("aria-valuenow", "25");
  await expect.element(progress).toHaveAttribute("aria-valuetext", "5 kB of 20 kB");
  await expect.element(screen.getByText("1 kB, waiting")).toBeVisible();
  await expect.element(screen.getByRole("note").first()).toHaveTextContent("Uploaded brief.docx.");
  await screen.getByRole("button", { name: "Stop uploading plan.xlsx" }).click();
  await screen.getByRole("button", { name: "Try again to upload scan.pdf" }).click();
  await screen.getByRole("button", { name: "Don't upload deck.pptx" }).click();
  await screen.getByRole("button", { name: "Dismiss brief.docx" }).click();
  expect(screen.getByRole("button", { name: "Try again to upload notes.txt" }).elements()).toEqual(
    [],
  );
  expect(done).toEqual(["stop 2", "retry 4", "remove 3", "remove 1"]);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a file sent with no bytes counted yet is at nothing, and no list is no list", async () => {
  const screen = await render(
    <UploadList
      items={[{ id: "1", name: "a.docx", size: 4, state: "sending" }]}
      onStop={() => undefined}
      onRemove={() => undefined}
      onRetry={() => undefined}
    />,
  );
  await expect.element(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  await screen.rerender(
    <UploadList
      items={[]}
      onStop={() => undefined}
      onRemove={() => undefined}
      onRetry={() => undefined}
    />,
  );
  expect(screen.container.querySelector("ul")).toBeNull();
});

test("a name is shown isolated, without the controls that would reorder what is around it", async () => {
  expect(plainName("a\u202Eb\u2066c\u200Fd.docx")).toBe("abcd.docx");
  const screen = await render(
    <UploadList
      items={[{ id: "1", name: "gpj\u202Ecod.exe", size: 4, state: "waiting" }]}
      onStop={() => undefined}
      onRemove={() => undefined}
      onRetry={() => undefined}
    />,
  );
  const shown = screen.container.querySelector("bdi");
  expect(shown?.textContent).toBe("gpjcod.exe");
});
