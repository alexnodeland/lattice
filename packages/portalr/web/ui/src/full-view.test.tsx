import { type ReactNode, useState } from "react";
import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Dialog } from "./dialog";
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
  // Shift+Tab enters a group with nothing checked where the browser has it (Chromium: the
  // first); either end of the group counts as its stop.
  expect(await named(true)).toBe("Warm");
});

test("a radio the browser wouldn't stop at, hidden or off, isn't its group's stop", async () => {
  const screen = await render(
    <Box>
      <input type="radio" name="pick" aria-label="Gone" style={{ visibility: "hidden" }} />
      <input type="radio" name="pick" aria-label="Shown" />
      <input type="radio" name="pick" aria-label="Off" disabled />
    </Box>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  await userEvent.tab();
  expect(document.activeElement?.getAttribute("aria-label")).toBe("Shown");
  await userEvent.tab();
  expect(focused()).toBe("Back to the page");
});

test("from past its last stop, as a control off the order, Tab still goes back to its first", async () => {
  const screen = await render(
    <Box>
      <button type="button">Inside</button>
      <button type="button" tabIndex={-1}>
        Roving
      </button>
    </Box>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  (screen.getByRole("button", { name: "Roving" }).element() as HTMLElement).focus();
  await userEvent.tab();
  expect(focused()).toBe("Back to the page");
  (screen.getByRole("button", { name: "Back to the page" }).element() as HTMLElement).focus();
  await userEvent.tab({ shift: true });
  expect(focused()).toBe("Inside");
});

test("a dialog opened from a full view keeps Tab and Shift+Tab to itself", async () => {
  function WithDialog() {
    const [open, setOpen] = useState(false);
    return (
      <Box>
        <button type="button" onClick={() => setOpen(true)}>
          Ask
        </button>
        <Dialog open={open} onOpenChange={setOpen} title="Sure?">
          <button type="button">Yes</button>
        </Dialog>
      </Box>
    );
  }
  const screen = await render(<WithDialog />);
  await screen.getByRole("button", { name: "Full view" }).click();
  await screen.getByRole("button", { name: "Ask" }).click();
  const dialog = screen.getByRole("dialog", { name: "Sure?" });
  await expect.poll(() => dialog.element().contains(document.activeElement)).toBe(true);
  for (const shift of [false, false, false, true, true, true]) {
    await userEvent.tab({ shift });
    expect(dialog.element().contains(document.activeElement)).toBe(true);
  }
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

test("a group of radios with nothing checked at the end of the box is its last stop, either radio", async () => {
  const screen = await render(
    <Box>
      <input type="radio" name="end" aria-label="North" />
      <input type="radio" name="end" aria-label="South" />
    </Box>,
  );
  await screen.getByRole("button", { name: "Full view" }).click();
  for (const radio of ["North", "South"]) {
    (screen.getByRole("radio", { name: radio }).element() as HTMLElement).focus();
    await userEvent.tab();
    expect(focused()).toBe("Back to the page");
  }
});
