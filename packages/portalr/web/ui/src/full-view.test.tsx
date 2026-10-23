import type { ReactNode } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { useFullView } from "./full-view";

function Box({ children, backInside = true }: { children?: ReactNode; backInside?: boolean }) {
  const { full, setFull, box, back } = useFullView();
  const backButton = (
    <button type="button" ref={back} onClick={() => setFull(!full)}>
      {full ? "Back to the page" : "Full view"}
    </button>
  );
  return (
    <>
      <button type="button">Before</button>
      {!backInside && backButton}
      <div ref={box}>
        {backInside && backButton}
        {children ?? <button type="button">Inside</button>}
      </div>
      <button type="button">After</button>
    </>
  );
}

const focused = () => document.activeElement?.textContent ?? document.activeElement?.tagName;

async function tabs(count: number, shift = false) {
  const seen: (string | undefined)[] = [];
  for (let step = 0; step < count; step++) {
    await userEvent.tab({ shift });
    seen.push(focused());
  }
  return seen;
}

test("in a full view, Tab goes round its own stops, never out to the page or the document", async () => {
  const screen = await render(<Box />);
  await screen.getByRole("button", { name: "Full view" }).click();
  expect(focused()).toBe("Back to the page");
  expect(await tabs(4)).toEqual(["Inside", "Back to the page", "Inside", "Back to the page"]);
  expect(await tabs(2, true)).toEqual(["Inside", "Back to the page"]);
});

test("what Tab doesn't stop at isn't its first or last: off the order, disabled, hidden, folded", async () => {
  const screen = await render(
    <Box>
      <button type="button">Inside</button>
      <button type="button" tabIndex={-1}>
        Roving
      </button>
      <button type="button" disabled>
        Off
      </button>
      <button type="button" style={{ visibility: "hidden" }}>
        Unseen
      </button>
      <details>
        <summary>More</summary>
        <button type="button">Folded</button>
      </details>
    </Box>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  expect(await tabs(3)).toEqual(["Inside", "More", "Back to the page"]);
  expect(await tabs(1, true)).toEqual(["More"]);
});

test("of a group of radios, Tab stops at the checked one, or the first, as the browser does", async () => {
  const screen = await render(
    <Box>
      <form>
        <input type="radio" name="size" aria-label="Small" />
        <input type="radio" name="size" aria-label="Large" defaultChecked />
      </form>
      <input type="radio" name="tone" aria-label="Warm" />
      <input type="radio" name="tone" aria-label="Cool" />
      <input type="radio" aria-label="Alone" />
    </Box>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  const named = async (shift = false) => {
    await userEvent.tab({ shift });
    return document.activeElement?.getAttribute("aria-label") ?? focused();
  };
  expect([await named(), await named(), await named(), await named()]).toEqual([
    "Large",
    "Warm",
    "Alone",
    "Back to the page",
  ]);
  expect(await named(true)).toBe("Alone");
});

test("Shift+Tab from outside the box goes to its last stop", async () => {
  const screen = await render(<Box />);
  await screen.getByRole("button", { name: "Full view" }).click();
  (document.body as HTMLElement).focus();
  (document.activeElement as HTMLElement | null)?.blur();
  await userEvent.tab({ shift: true });
  expect(focused()).toBe("Inside");
});

test("a box with no stop of its own leaves Tab to the browser", async () => {
  const screen = await render(
    <Box backInside={false}>
      <p>Words alone</p>
    </Box>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  await userEvent.tab();
  expect(document.activeElement?.closest("[inert]")).toBeNull();
});

test("back in the page, Tab goes on as the page has it", async () => {
  const screen = await render(<Box />);
  await screen.getByRole("button", { name: "Full view" }).click();
  await screen.getByRole("button", { name: "Back to the page" }).click();
  expect(await tabs(2)).toEqual(["Inside", "After"]);
});
