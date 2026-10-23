import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { FailureAlert } from "./failure-alert";

const HOSTILE = `${String.fromCodePoint(0x202e)}<img src=x onerror=alert(1)>\npassword=hunter2`;

test("a failure says what didn't happen and the kit's sentence, never the server's words", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  try {
    const read = Object.assign(new Error(HOSTILE), {
      status: 503,
      detail: HOSTILE,
      said: "The server had a problem. Try again in a moment.",
    });
    const screen = await render(
      <>
        <FailureAlert lead="The links couldn't be made." error={read} />
        <FailureAlert error={{ status: 400, detail: HOSTILE }} />
      </>,
    );
    const [first, second] = screen.getByRole("alert").elements();
    expect(first?.textContent).toBe(
      "The links couldn't be made. The server had a problem. Try again in a moment.",
    );
    expect(second?.textContent).toBe("Something went wrong. Try again in a moment.");
    for (const alert of [first, second]) {
      for (const part of ["hunter2", "img", String.fromCodePoint(0x202e)]) {
        expect(alert?.textContent).not.toContain(part);
      }
    }
    await expect.poll(() => warned.mock.calls.length).toBe(2);
    expect(String(warned.mock.calls[0]?.[1])).not.toContain("hunter2");
  } finally {
    warned.mockRestore();
  }
});
