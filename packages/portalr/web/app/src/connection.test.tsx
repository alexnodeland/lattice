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

test("a stream that closed offers to connect now, where the page can, and one connecting again says what is sent waits", async () => {
  const onReconnect = vi.fn();
  const screen = await render(
    <Connection
      snapshot={{ state: null, seq: 3, status: "closed", error: null }}
      waiting="the workspace"
      onReconnect={onReconnect}
    />,
  );
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("The connection to this workspace ended.Connect now");
  await screen.getByRole("button", { name: "Connect now" }).click();
  expect(onReconnect).toHaveBeenCalledOnce();
  await screen.rerender(
    <Connection
      snapshot={{ state: null, seq: 3, status: "connecting", error: null }}
      waiting="the workspace"
      onReconnect={onReconnect}
    />,
  );
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("Connecting again… What you send goes once it is connected.");
  // Before the log was ever read, connecting is reading.
  await screen.rerender(
    <Connection
      snapshot={{ state: null, seq: 0, status: "connecting", error: null }}
      waiting="the workspace"
    />,
  );
  await expect.element(screen.getByRole("status")).toHaveTextContent("Reading the workspace…");
});

test("offline, the notice says so rather than blaming the connection", async () => {
  const was = Object.getOwnPropertyDescriptor(Navigator.prototype, "onLine");
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false });
  try {
    const screen = await render(
      <Connection
        snapshot={{ state: null, seq: 3, status: "closed", error: null }}
        waiting="the workspace"
        onReconnect={() => undefined}
      />,
    );
    const said = screen.getByRole("alert");
    await expect.poll(() => said.element().textContent).toContain("You're offline.");
    expect(said.element().textContent).not.toContain("connection to this workspace");
  } finally {
    // The instance's own getter goes, and the prototype's shows through again.
    Reflect.deleteProperty(navigator, "onLine");
    if (was) {
      Object.defineProperty(Navigator.prototype, "onLine", was);
    }
  }
});
