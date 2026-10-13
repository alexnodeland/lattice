import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Account } from "./account";

test("the account is named by the session's email, and signs it out", async () => {
  const signOut = vi.fn(async () => undefined);
  const screen = await render(<Account signed={{ email: () => "alice@acme.test", signOut }} />);
  await screen.getByRole("button", { name: "Account: alice@acme.test" }).click();
  await screen.getByRole("menuitem", { name: "Sign out" }).click();
  expect(signOut).toHaveBeenCalledOnce();
});
