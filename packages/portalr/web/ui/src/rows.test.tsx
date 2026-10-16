import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Row, RowLink, Rows } from "./rows";
import { contrast, token } from "./test/colours";

test("rows are a named list, each row's link named by its words alone", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row>
        <RowLink href="#launch">Launch plan</RowLink>
        <span>Waiting for you</span>
      </Row>
    </Rows>,
  );
  const list = screen.getByRole("list", { name: "Threads" });
  await expect.element(list.getByRole("listitem")).toHaveTextContent("Launch planWaiting for you");
  await expect.element(list.getByRole("link", { name: "Launch plan" })).toBeVisible();
});

test("a row's link takes the whole row: a click on the row's far side follows it", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row>
        <RowLink href="#launch">Launch plan</RowLink>
      </Row>
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
      <Row>
        <RowLink href="#thread">Launch plan</RowLink>
      </Row>
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
