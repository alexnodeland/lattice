import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Alert, type AlertTone } from "./alert";
import { Reading, Skeleton } from "./skeleton";
import { contrast, token } from "./test/colours";

const TONES: readonly AlertTone[] = ["info", "warn", "error"];

test("an error is an alert, and a note and a warning are statuses, each said in its words alone", async () => {
  const screen = await render(
    <>
      <Alert tone="error">The tenant wasn't created.</Alert>
      <Alert tone="warn">These are the newest.</Alert>
      <Alert>Saved.</Alert>
    </>,
  );
  await expect.element(screen.getByRole("alert")).toHaveTextContent("The tenant wasn't created.");
  const notes = screen
    .getByRole("status")
    .elements()
    .map((note) => note.textContent);
  expect(notes).toEqual(["These are the newest.", "Saved."]);
});

test("an alert that is part of what the page reads is a note, never a live region", async () => {
  const screen = await render(
    <Alert tone="error" live={false}>
      Don't run this twice.
    </Alert>,
  );
  await expect.element(screen.getByRole("note")).toHaveTextContent("Don't run this twice.");
  expect(screen.container.querySelector("[role=alert], [role=status]")).toBeNull();
});

test("each tone has a shape of its own beside its words, hidden from assistive technology", async () => {
  const screen = await render(
    <div>
      {TONES.map((tone) => (
        <Alert key={tone} tone={tone}>
          {tone}
        </Alert>
      ))}
    </div>,
  );
  const shapes = TONES.map((tone) => {
    const icon = screen.getByText(tone).element().parentElement?.querySelector("svg");
    expect(icon?.getAttribute("aria-hidden")).toBe("true");
    return icon?.innerHTML;
  });
  expect(new Set(shapes).size).toBe(3);
});

test("its words are in the ink and read on the surface; the colour is the edge, a mark", async () => {
  const screen = await render(
    <div>
      {TONES.map((tone) => (
        <Alert key={tone} tone={tone}>
          {tone}
        </Alert>
      ))}
    </div>,
  );
  const edges = { info: token("edge"), warn: token("status-warn"), error: token("status-failed") };
  for (const tone of TONES) {
    const style = getComputedStyle(screen.getByText(tone).element().parentElement as Element);
    expect(style.color).toBe(token("fg"));
    expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(7);
    expect(style.borderLeftColor).toBe(edges[tone]);
    expect(contrast(style.borderLeftColor, token("surface"))).toBeGreaterThanOrEqual(3);
  }
});

test("a skeleton is hidden from assistive technology, and pulses unless motion is reduced", async () => {
  onTestFinished(() => commands.reduceMotion(true));
  const screen = await render(<Skeleton className="h-4 w-24" />);
  const bar = screen.container.firstElementChild as Element;
  expect(bar.getAttribute("aria-hidden")).toBe("true");
  expect(getComputedStyle(bar).animationName).toBe("none");
  await commands.reduceMotion(false);
  expect(getComputedStyle(bar).animationName).toBe("pulse");
  expect(getComputedStyle(bar).backgroundColor).toBe(token("line"));
});

test("what is being read is a status in words, over placeholders, which say nothing themselves", async () => {
  const screen = await render(<Reading>Reading the workspace's runs…</Reading>);
  const status = screen.getByRole("status");
  await expect.element(status).toHaveTextContent("Reading the workspace's runs…");
  expect(status.element().querySelectorAll("[aria-hidden='true']")).toHaveLength(2);
});
