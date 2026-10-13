import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { ThreadMenu } from "./thread-menu";

const done = { outcome: "done", result: { seq: 1 } } as never;

test("the menu offers what may be done: sharing, and restricting by whether it is", async () => {
  const share = vi.fn();
  const restrict = vi.fn(async () => done);
  const screen = await render(
    <ThreadMenu restricted={false} onRestrict={restrict} onShare={share} />,
  );
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await screen.getByRole("menuitem", { name: "Restrict" }).click();
  expect(restrict).toHaveBeenCalledOnce();
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await screen.getByRole("menuitem", { name: "Share…" }).click();
  expect(share).toHaveBeenCalledOnce();
});

test("a restricted thread's item lifts it, and a refusal is said", async () => {
  const screen = await render(
    <ThreadMenu
      restricted
      onRestrict={async () => ({ outcome: "refused", status: 403, reasons: ["not yours"] })}
      onShare={null}
    />,
  );
  await screen.getByRole("button", { name: "Thread actions" }).click();
  await expect.element(screen.getByRole("menuitem", { name: "Share…" })).not.toBeInTheDocument();
  await screen.getByRole("menuitem", { name: "Lift restriction" }).click();
  await expect.element(screen.getByRole("alert")).toHaveTextContent("That wasn't done: not yours");
});

test("someone who may do nothing sees no menu", async () => {
  const screen = await render(<ThreadMenu restricted={null} onRestrict={vi.fn()} onShare={null} />);
  await expect.element(screen.getByRole("button")).not.toBeInTheDocument();
});
