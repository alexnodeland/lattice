import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { RunStatus } from "./chat";
import { Row, RowLink, Rows } from "./rows";
import { contrast, token } from "./test/colours";

test("rows are a named list, each row's link named by its words alone", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row
        name={<RowLink href="#launch">Launch plan</RowLink>}
        end={<span>Waiting for you</span>}
      />
    </Rows>,
  );
  const list = screen.getByRole("list", { name: "Threads" });
  await expect.element(list.getByRole("listitem")).toHaveTextContent("Launch planWaiting for you");
  await expect.element(list.getByRole("link", { name: "Launch plan" })).toBeVisible();
});

test("a row's link takes the whole row: a click on the row's far side follows it", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row name={<RowLink href="#launch">Launch plan</RowLink>} />
    </Rows>,
  );
  const row = screen.getByRole("listitem").element();
  const box = row.getBoundingClientRect();
  const hit = document.elementFromPoint(box.right - 4, box.top + box.height / 2);
  expect(hit?.closest("a")?.getAttribute("href")).toBe("#launch");
});

test("a row's link shows the focus ring over the whole row when the keyboard reaches it", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row name={<RowLink href="#thread">Launch plan</RowLink>} />
    </Rows>,
  );
  await userEvent.tab();
  const link = screen.getByRole("link", { name: "Launch plan" }).element();
  expect(link.matches(":focus-visible")).toBe(true);
  const ring = getComputedStyle(link, "::after");
  expect(ring.outlineStyle).not.toBe("none");
  expect(ring.outlineColor).toBe(token("focus"));
  expect(Number.parseFloat(ring.outlineWidth)).toBeGreaterThanOrEqual(2);
  expect(contrast(ring.outlineColor, token("surface"))).toBeGreaterThanOrEqual(3);
});

test("a row's name is a quiet link, its meta quieter on the line beneath", async () => {
  const screen = await render(
    <Rows label="Artifacts">
      <Row name={<RowLink href="#a">Launch plan</RowLink>} meta="art_1, note, version 2" />
    </Rows>,
  );
  const link = screen.getByRole("link", { name: "Launch plan" }).element();
  expect(getComputedStyle(link).color).toBe(token("fg"));
  // A quiet underline at rest, so it reads as a link where nothing hovers.
  expect(getComputedStyle(link).textDecorationLine).toBe("underline");
  expect(getComputedStyle(link).textDecorationColor).toBe(token("edge"));
  const meta = screen.getByText("art_1, note, version 2").element();
  expect(getComputedStyle(meta).color).toBe(token("muted"));
  expect(meta.getBoundingClientRect().top).toBeGreaterThan(link.getBoundingClientRect().bottom - 1);
  await userEvent.hover(link);
  expect(getComputedStyle(link).color).toBe(token("accent"));
  expect(getComputedStyle(link).textDecorationColor).toBe(token("accent"));
});

test("a row's name takes the working colour when the keyboard reaches it", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row name={<RowLink href="#a">Launch plan</RowLink>} />
    </Rows>,
  );
  await userEvent.tab();
  const link = screen.getByRole("link", { name: "Launch plan" }).element();
  expect(link.matches(":focus-visible")).toBe(true);
  expect(getComputedStyle(link).color).toBe(token("accent"));
  expect(getComputedStyle(link).textDecorationColor).toBe(token("accent"));
});

test("what is at a row's end is a target of its own, above the row's link", async () => {
  onTestFinished(() => history.replaceState(null, "", location.pathname + location.search));
  let pressed = false;
  const screen = await render(
    <Rows label="People">
      <Row
        name={<RowLink href="#alice">alice</RowLink>}
        end={
          <button type="button" onClick={() => (pressed = true)}>
            Revoke
          </button>
        }
      />
    </Rows>,
  );
  const button = screen.getByRole("button", { name: "Revoke" }).element();
  const box = button.getBoundingClientRect();
  // What is under the pointer at the button's middle is the button, not the stretched link.
  expect(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)).toBe(
    button,
  );
  await screen.getByRole("button", { name: "Revoke" }).click();
  expect(pressed).toBe(true);
  expect(location.hash).not.toBe("#alice");
});

test("on a phone, a row's end goes under its meta, and its name keeps the width", async () => {
  await page.viewport(320, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <Rows label="Rules">
      <Row
        name={<RowLink href="#r">nightly-digest-of-everything</RowLink>}
        meta="stored, version 3"
        end={<span>12 behind, 3 dead letters</span>}
      />
    </Rows>,
  );
  // The name's line is the row's width, less its padding: nothing at its end takes from it.
  const row = screen.getByRole("listitem").element().getBoundingClientRect();
  const name = (
    screen.getByRole("link").element().parentElement as Element
  ).getBoundingClientRect();
  const end = screen.getByText("12 behind, 3 dead letters").element().getBoundingClientRect();
  const meta = screen.getByText("stored, version 3").element().getBoundingClientRect();
  expect(end.top).toBeGreaterThanOrEqual(meta.bottom - 1);
  expect(name.width).toBeGreaterThanOrEqual(row.width - 16);
});

test("on a phone, a row's name of several blocks is all there: none of it is clipped", async () => {
  await page.viewport(320, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <Rows label="Runs">
      <Row
        name={
          <>
            <code>portalr:triage</code>, retried three times.{" "}
            <span>last failure: the tracker refused the item, after three tries.</span> Filed as{" "}
            <a href="#ops-12">OPS-12</a>
          </>
        }
        end={<span>Dead-lettered</span>}
      />
    </Rows>,
  );
  const row = screen.getByRole("listitem").element().getBoundingClientRect();
  for (const part of [
    screen.getByText(/last failure/).element(),
    screen.getByRole("link", { name: "OPS-12" }).element(),
  ]) {
    const box = part.getBoundingClientRect();
    expect(box.top).toBeGreaterThanOrEqual(row.top);
    expect(box.bottom).toBeLessThanOrEqual(row.bottom);
    // And drawn there: what is at its middle is it, not what a clip would leave.
    const hit = document.elementFromPoint(box.left + 4, box.top + box.height / 2);
    expect(part.contains(hit)).toBe(true);
  }
});

test("wider, a row's end takes half the row at most", async () => {
  await page.viewport(700, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <Rows label="Rules">
      <Row
        name={<RowLink href="#r">digest</RowLink>}
        end={<span>{"12 behind, 3 dead letters, ".repeat(6)}</span>}
      />
    </Rows>,
  );
  const row = screen.getByRole("listitem").element().getBoundingClientRect();
  const end = (
    screen.getByText(/12 behind/).element().parentElement as Element
  ).getBoundingClientRect();
  expect(end.width).toBeLessThanOrEqual(row.width / 2 + 1);
});

test("what is at a row's end sits against the row's end, however wide the row", async () => {
  await page.viewport(1280, 800);
  onTestFinished(() => page.viewport(414, 896));
  for (const width of [1100, 700]) {
    const screen = await render(
      <div style={{ width }}>
        <Rows label={`Threads ${width}`}>
          <Row name={<RowLink href="#a">A tour</RowLink>} end={<RunStatus status="paused" />} />
        </Rows>
      </div>,
    );
    const list = screen.getByRole("list", { name: `Threads ${width}` });
    const row = list.getByRole("listitem").element();
    const status = row.querySelector("[role=status]") as HTMLElement;
    const badge = status.getBoundingClientRect();
    const end =
      row.getBoundingClientRect().right - Number.parseFloat(getComputedStyle(row).paddingRight);
    expect(Math.abs(badge.right - end)).toBeLessThan(1);
    // And it is within its column, not spilling out of it towards the name.
    const column = (status.parentElement as HTMLElement).getBoundingClientRect();
    expect(badge.left).toBeGreaterThanOrEqual(column.left - 0.5);
  }
});

test("an end of several controls sits against the row's end, and wraps within half the row", async () => {
  await page.viewport(1280, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <div style={{ width: 900 }}>
      <Rows label="Uploads">
        <Row
          name={<RowLink href="#u">brief.docx</RowLink>}
          meta="Word document, 48 kB"
          end={
            <>
              <span>Uploaded</span>
              <button type="button">Open</button>
              <button type="button">Remove</button>
            </>
          }
        />
        <Row
          name={<RowLink href="#w">a-very-long-name-that-takes-the-row.xlsx</RowLink>}
          end={<span>{"3 sheets, 12 tables, 2 charts, ".repeat(5)}</span>}
        />
      </Rows>
    </div>,
  );
  const rows = screen.getByRole("listitem").elements();
  const [first, second] = rows as [HTMLElement, HTMLElement];
  const edge = (row: HTMLElement) =>
    row.getBoundingClientRect().right - Number.parseFloat(getComputedStyle(row).paddingRight);
  const remove = screen.getByRole("button", { name: "Remove" }).element().getBoundingClientRect();
  expect(Math.abs(remove.right - edge(first))).toBeLessThan(1);
  // Each control keeps its own target, above the row's link.
  const open = screen.getByRole("button", { name: "Open" }).element();
  const box = open.getBoundingClientRect();
  expect(document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2)).toBe(open);
  // A long end wraps within half the row, and the name keeps the other half.
  const end = (
    screen.getByText(/3 sheets/).element().parentElement as HTMLElement
  ).getBoundingClientRect();
  expect(end.width).toBeLessThanOrEqual(second.getBoundingClientRect().width / 2 + 1);
  expect(Math.abs(end.right - edge(second))).toBeLessThan(1);
});
