import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Messages } from "./chat";
import { RunFailed } from "./run-failed";

test("a failed turn says why in words, the run's own short error with it, and can be tried again", async () => {
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
    .element(screen.getByRole("alert").getByRole("paragraph").first())
    .toHaveTextContent(
      "The assistant couldn't finish. The model kept calling a tool in a way the tool refused, and ran out of tries.",
    );
  // Short, the error is said in the alert itself, with no Details to open.
  await expect.element(screen.getByText(/exceeded max retries/)).toBeVisible();
  expect(screen.getByText("Details").elements()).toHaveLength(0);
  await screen.getByRole("button", { name: "Try again" }).click();
  expect(onRetry).toHaveBeenCalledOnce();
});

test("a long error, or one of several lines, waits under Details", async () => {
  const screen = await render(
    <Messages>
      <RunFailed reason={null} error={"Traceback (most recent call last):\n  boom"} />
      <RunFailed reason={null} error={`ModelHTTPError: ${"overloaded ".repeat(20)}`} />
    </Messages>,
  );
  expect(screen.getByText("Details").elements()).toHaveLength(2);
  await expect.element(screen.getByText(/Traceback/)).not.toBeVisible();
  await screen.getByText("Details").first().click();
  await expect.element(screen.getByText(/Traceback/)).toBeVisible();
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
  await expect.element(screen.getByText("Boom")).toBeVisible();
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

test("a failure the thread says is live is announced, whoever may try again", async () => {
  const screen = await render(
    <Messages>
      <RunFailed reason="abandoned" error={null} live />
      <RunFailed reason="abandoned" error={null} live={false} retryRefused="Not here." />
    </Messages>,
  );
  await expect
    .poll(() => screen.getByRole("alert").element().textContent)
    .toContain("The turn stopped answering, and was given up.");
  expect(screen.getByRole("alert").elements()).toHaveLength(1);
  expect(screen.getByRole("note").elements()).toHaveLength(1);
});
