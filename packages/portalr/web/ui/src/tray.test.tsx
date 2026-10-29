import type { ReactNode } from "react";
import { afterEach, expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { reachWaiting, Tray } from "./tray";

const question = (
  <div key="q" id="request-q" tabIndex={-1}>
    <section aria-label="The agent asks">Which week?</section>
  </div>
);
const proposal = (
  <section key="p" id="proposal-p" tabIndex={-1}>
    Add a closing line
  </section>
);
const SOME = [
  { label: "Which week?", children: question },
  { label: "Add a closing line", children: proposal },
];

afterEach(() => {
  history.replaceState(null, "", location.pathname);
});

const waiting = (...children: ReactNode[]) =>
  children.map((each, at) => ({ label: `Waiting ${at + 1}`, children: each }));

test("nothing waiting draws nothing, but keeps its status, so what arrives is announced", async () => {
  const screen = await render(<Tray waiting={[]} />);
  expect(screen.container.querySelector("section")).toBeNull();
  await expect.element(screen.getByRole("status")).toHaveTextContent("");
  await screen.rerender(<Tray waiting={SOME.slice(0, 1)} />);
  await expect.element(screen.getByRole("status")).toHaveTextContent("1 waiting for you");
  await screen.rerender(<Tray waiting={SOME} />);
  await expect.element(screen.getByRole("status")).toHaveTextContent("2 waiting for you");
});

test("one thing waiting is shown whole, with no line that counts it", async () => {
  const screen = await render(<Tray waiting={SOME.slice(0, 1)} />);
  await expect.element(screen.getByRole("region", { name: "The agent asks" })).toBeVisible();
  expect(screen.getByRole("button").elements()).toHaveLength(0);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("several are one line, counted, that opens to all of them", async () => {
  const screen = await render(<Tray waiting={SOME} />);
  const line = screen.getByRole("button", { name: /2 waiting for you/ });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  expect(line.element().textContent).toContain("Which week? · Add a closing line");
  expect(line.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  const closing = screen
    .getByRole("region", { name: "Waiting for you" })
    .getByText("Add a closing line", { exact: true });
  await expect.element(closing).not.toBeVisible();
  await line.click();
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect.element(closing).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
  await line.click();
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
});

test("it scrolls inside itself, never less than a few lines tall, and its last control is reachable", async () => {
  const tall = (
    <div key="t">
      <div style={{ height: "200vh" }}>Tall</div>
      <button type="button">Last</button>
    </div>
  );
  const screen = await render(<Tray waiting={waiting(tall)} />);
  const body = screen.getByText("Tall", { exact: true }).element().parentElement
    ?.parentElement as HTMLElement;
  const box = body.getBoundingClientRect();
  expect(box.height).toBeLessThanOrEqual(window.innerHeight * 0.4 + 1);
  expect(getComputedStyle(body).overflowY).toBe("auto");
  expect(getComputedStyle(body).overflowX).toBe("hidden");
  // Past it: scrolled to the end, the last control is in its view, and it fades where more is past.
  body.scrollTo(0, body.scrollHeight);
  const last = screen.getByRole("button", { name: "Last" }).element().getBoundingClientRect();
  expect(last.bottom).toBeLessThanOrEqual(box.bottom);
  expect(last.top).toBeGreaterThanOrEqual(box.top);
  expect(getComputedStyle(body).maskImage).toContain("linear-gradient");
  // Never less than nine rem, however little the window has left of its height.
  document.documentElement.style.setProperty("--keyboard-inset", `${window.innerHeight - 40}px`);
  expect(body.getBoundingClientRect().height).toBeGreaterThanOrEqual(143);
  document.documentElement.style.removeProperty("--keyboard-inset");
});

test("a focus ring at the tray's edge isn't cut: its padding clears it", async () => {
  const screen = await render(
    <Tray
      waiting={waiting(
        <button key="b" type="button">
          Edge
        </button>,
      )}
    />,
  );
  const body = screen.getByRole("button", { name: "Edge" }).element().parentElement as HTMLElement;
  const style = getComputedStyle(body);
  expect(Number.parseFloat(style.paddingTop)).toBeGreaterThanOrEqual(4);
  expect(Number.parseFloat(style.paddingLeft)).toBeGreaterThanOrEqual(4);
});

test("a hash the page opens at, and a link to it shut again, open the tray and bring the focus to it", async () => {
  location.hash = "#proposal-p";
  const screen = await render(
    <>
      <a href="#proposal-p">Review</a>
      <Tray waiting={SOME} />
    </>,
  );
  const line = screen.getByRole("button", { name: /2 waiting/ });
  // Opened at mount, where the page was opened at it.
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect.poll(() => document.activeElement?.id).toBe("proposal-p");
  await line.click();
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  // The hash is the same: no change comes, and the link's click is what opens it.
  await screen.getByRole("link", { name: "Review" }).click();
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect.poll(() => document.activeElement?.id).toBe("proposal-p");
});

test("reaching a request, as Go to the question does, opens the tray and focuses its card's first named part", async () => {
  const screen = await render(<Tray waiting={SOME} />);
  const line = screen.getByRole("button", { name: /2 waiting/ });
  // What is no part of a tray, or of the page, is reached as it can be, and no harm.
  reachWaiting("request-missing");
  reachWaiting("request-q");
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect
    .poll(() => document.activeElement?.getAttribute("aria-label"))
    .toBe("The agent asks");
});

test("what is open stays open as another arrives, the reader's place kept; several at first are closed", async () => {
  const typing = (
    <label key="q" id="request-q">
      Answer <input />
    </label>
  );
  const screen = await render(<Tray waiting={waiting(typing)} />);
  const input = screen.getByRole("textbox").element() as HTMLInputElement;
  input.focus();
  await userEvent.keyboard("Tuesday");
  // A proposal arrives as the reader types: the card isn't hidden, nor the focus dropped.
  await screen.rerender(<Tray waiting={waiting(typing, proposal)} />);
  const line = screen.getByRole("button", { name: /2 waiting/ });
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("textbox").element()).toBe(input);
  expect(document.activeElement).toBe(input);
  expect(input.value).toBe("Tuesday");
  // Back to one, and to none, and to two at once: closed, as several are at first.
  await screen.rerender(<Tray waiting={waiting(typing)} />);
  expect(screen.getByRole("button").elements()).toHaveLength(0);
  await screen.rerender(<Tray waiting={[]} />);
  await screen.rerender(<Tray waiting={SOME} />);
  await expect
    .element(screen.getByRole("button", { name: /2 waiting/ }))
    .toHaveAttribute("aria-expanded", "false");
});
