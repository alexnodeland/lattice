import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Row, RowLink, Rows } from "./rows";
import { contrast, token } from "./test/colours";

test("rows are a named list, each row's link named by its words alone", async () => {
  const screen = await render(
    <Rows label="Threads">
      <Row
        title={<RowLink href="#launch">Launch plan</RowLink>}
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
      <Row title={<RowLink href="#launch">Launch plan</RowLink>} />
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
      <Row title={<RowLink href="#thread">Launch plan</RowLink>} />
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

test("a row's title is in the text's colour, its meta quieter on the line beneath", async () => {
  const screen = await render(
    <Rows label="Artifacts">
      <Row title={<RowLink href="#a">Launch plan</RowLink>} meta="art_1, note, version 2" />
    </Rows>,
  );
  const link = screen.getByRole("link", { name: "Launch plan" }).element();
  expect(getComputedStyle(link).color).toBe(token("fg"));
  expect(getComputedStyle(link).textDecorationLine).toBe("none");
  const meta = screen.getByText("art_1, note, version 2").element();
  expect(getComputedStyle(meta).color).toBe(token("muted"));
  expect(meta.getBoundingClientRect().top).toBeGreaterThan(link.getBoundingClientRect().bottom - 1);
  await userEvent.hover(link);
  expect(getComputedStyle(link).color).toBe(token("accent"));
  expect(getComputedStyle(link).textDecorationLine).toBe("underline");
});

test("what is at a row's end is a target of its own, above the row's link", async () => {
  let pressed = false;
  const screen = await render(
    <Rows label="People">
      <Row
        title={<RowLink href="#alice">alice</RowLink>}
        end={
          <button type="button" onClick={() => (pressed = true)}>
            Revoke
          </button>
        }
      />
    </Rows>,
  );
  await screen.getByRole("button", { name: "Revoke" }).click();
  expect(pressed).toBe(true);
});
