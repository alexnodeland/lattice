import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Messages } from "./chat";
import { RunFailed } from "./run-failed";

test("a failed turn says why in words, the run's own under Details, and can be tried again", async () => {
  const onRetry = vi.fn(async () => ({ outcome: "done" }) as const);
  const screen = await render(
    <Messages>
      <RunFailed
        reason="tool_retries_exhausted"
        error="Tool 'draft_rule' exceeded max retries count of 1"
        onRetry={onRetry}
      />
    </Messages>,
  );
  await expect
    .element(screen.getByRole("alert").getByRole("paragraph"))
    .toHaveTextContent(
      "The assistant couldn't finish. The model kept calling a tool in a way the tool refused, and ran out of tries.",
    );
  await expect.element(screen.getByText(/exceeded max retries/)).not.toBeVisible();
  await screen.getByText("Details").click();
  await expect.element(screen.getByText(/exceeded max retries/)).toBeVisible();
  await screen.getByRole("button", { name: "Try again" }).click();
  expect(onRetry).toHaveBeenCalledOnce();
});

test("a failure further up, or one without a reason, is a note, with no way to try again", async () => {
  const screen = await render(
    <Messages>
      <RunFailed reason={null} error={null} />
      <RunFailed reason="something_new" error="Boom" />
      <RunFailed reason="unexpected_model_behavior" error={null} />
    </Messages>,
  );
  const [plain, unknown, unusable] = screen.getByRole("note").elements();
  expect(unusable?.textContent).toContain("The model answered in a way the turn couldn't use.");
  expect(plain?.textContent).toContain("Something went wrong before it answered.");
  expect(unknown?.textContent).toContain("Something went wrong before it answered.");
  expect(screen.getByText("Details").elements()).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Try again" }).elements()).toHaveLength(0);
  expect(screen.getByRole("alert").elements()).toHaveLength(0);
});

test("a latest turn that can't be tried again says why, in place of the button", async () => {
  const screen = await render(
    <Messages>
      <RunFailed reason={null} error={null} retryRefused="It can't be tried again here." />
    </Messages>,
  );
  await expect
    .poll(() => screen.getByRole("alert").element().textContent)
    .toContain("It can't be tried again here.");
  expect(screen.getByRole("button", { name: "Try again" }).elements()).toHaveLength(0);
});
