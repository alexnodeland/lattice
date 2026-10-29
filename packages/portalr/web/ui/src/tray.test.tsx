import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { Tray } from "./tray";

const SOME = [
  { key: "q", label: "A question", children: <p id="request-q">Which week?</p> },
  {
    key: "p",
    label: "Add a closing line",
    children: <p id="proposal-p">Add a closing line</p>,
  },
];

test("nothing waiting draws nothing", async () => {
  const screen = await render(<Tray waiting={[]} />);
  expect(screen.container.querySelector("section")).toBeNull();
});

test("one thing waiting is shown whole, with no line that counts it", async () => {
  const screen = await render(<Tray waiting={SOME.slice(0, 1)} />);
  await expect.element(screen.getByText("Which week?")).toBeVisible();
  expect(screen.getByRole("button").elements()).toHaveLength(0);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("several are one line, counted, that opens to all of them", async () => {
  const screen = await render(<Tray waiting={SOME} />);
  const line = screen.getByRole("button", { name: /2 waiting for you/ });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  expect(line.element().textContent).toContain("A question · Add a closing line");
  expect(line.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  // Closed, none of them is shown: what they hold is out of reach, and of a reader's way.
  await expect.element(screen.getByText("Which week?")).not.toBeVisible();
  await line.click();
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect.element(screen.getByText("Which week?")).toBeVisible();
  await expect
    .element(screen.getByText("Add a closing line", { exact: true }).last())
    .toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
  await line.click();
  await expect.element(screen.getByText("Which week?")).not.toBeVisible();
});

test("it scrolls inside itself past a share of the window, so the composer keeps its room", async () => {
  const tall = [{ key: "t", label: "Tall", children: <div style={{ height: "200vh" }}>Tall</div> }];
  const screen = await render(<Tray waiting={tall} />);
  const body = screen.getByText("Tall", { exact: true }).element().parentElement;
  expect(body?.getBoundingClientRect().height).toBeLessThanOrEqual(window.innerHeight * 0.4 + 1);
  expect(getComputedStyle(body as Element).overflowY).toBe("auto");
});

test("a link to one of them, closed, opens the tray and brings the focus to it", async () => {
  const link = [
    { key: "q", label: "A question", children: <p id="request-q">Which week?</p> },
    {
      key: "p",
      label: "Add a closing line",
      children: (
        <section id="proposal-p" tabIndex={-1}>
          Add a closing line
        </section>
      ),
    },
  ];
  const screen = await render(<Tray waiting={link} />);
  await expect
    .element(screen.getByRole("button", { name: /2 waiting/ }))
    .toHaveAttribute("aria-expanded", "false");
  location.hash = "#proposal-p";
  await expect
    .element(screen.getByRole("button", { name: /2 waiting/ }))
    .toHaveAttribute("aria-expanded", "true");
  await expect.poll(() => document.activeElement?.id).toBe("proposal-p");
  history.replaceState(null, "", location.pathname);
});
