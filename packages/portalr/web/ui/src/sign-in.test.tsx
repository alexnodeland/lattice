import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { SignIn } from "./sign-in";

test("signing in sends the email and password, and says why it was refused", async () => {
  const onSignIn = vi.fn(async () => "Invalid login credentials");
  const screen = await render(<SignIn ui="admin" onSignIn={onSignIn} />);
  await screen.getByLabelText("Email").fill("alice@portalr.test");
  await screen.getByLabelText("Password").fill("secret");
  await screen.getByRole("button", { name: "Sign in" }).click();
  expect(onSignIn).toHaveBeenCalledExactlyOnceWith("alice@portalr.test", "secret");
  await expect
    .element(screen.getByLabelText("Password"))
    .toHaveAccessibleDescription("Invalid login credentials");
  await expect.element(screen.getByLabelText("Email")).toHaveValue("alice@portalr.test");
});
