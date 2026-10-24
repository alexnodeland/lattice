import { StrictMode } from "react";
import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Unanswered } from "./unanswered";

test("a tool that didn't answer is said politely, in its words, and why goes to the console once", async () => {
  const warned = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  const reading = { status: "unavailable", reason: "loki answered 502" } as const;
  const screen = await render(
    <StrictMode>
      <Unanswered tool="Loki" reading={reading} />
    </StrictMode>,
  );
  await expect
    .element(screen.getByRole("status").getByRole("heading", { name: "Loki isn't answering" }))
    .toBeVisible();
  expect(screen.getByText("loki answered 502").elements()).toHaveLength(0);
  await screen.rerender(
    <StrictMode>
      <Unanswered tool="Loki" reading={reading} />
    </StrictMode>,
  );
  await screen.unmount();
  await render(<Unanswered tool="Loki" reading={reading} />);
  // StrictMode's second effect, a render again, and a mount again: one line, for the one reading.
  await expect.poll(() => warned.mock.calls.length).toBe(1);
  expect(String(warned.mock.calls[0])).toContain("Loki: loki answered 502");
  warned.mockRestore();
});
