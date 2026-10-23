import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Connection } from "./workspace";

const HOSTILE = `${String.fromCodePoint(0x202e)}<img src=x onerror=alert(1)>\npassword=hunter2`;

test("a stream that closed says so, and its server's words go to the console alone", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => {});
  try {
    const screen = await render(
      <Connection
        snapshot={{ state: null, seq: 0, status: "closed", error: HOSTILE }}
        waiting="the workspace"
      />,
    );
    const alert = screen.getByRole("alert");
    await expect
      .element(alert)
      .toHaveTextContent(
        "The connection to this workspace ended. Reload the page to connect again.",
      );
    for (const part of ["hunter2", "img", String.fromCodePoint(0x202e)]) {
      expect(alert.element().textContent).not.toContain(part);
    }
    await expect.poll(() => warned.mock.calls.length).toBe(1);
    expect(String(warned.mock.calls[0]?.[1])).not.toContain("hunter2");
  } finally {
    warned.mockRestore();
  }
});
