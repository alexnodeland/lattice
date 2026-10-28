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
    .element(screen.getByRole("alert").getByRole("paragraph").first())
    .toHaveTextContent(
      "The assistant couldn't finish. The model kept calling a tool in a way the tool refused, and ran out of tries.",
    );
  await expect.element(screen.getByText(/exceeded max retries/)).not.toBeVisible();
  await screen.getByText("Details").click();
  await expect.element(screen.getByText(/exceeded max retries/)).toBeVisible();
  await screen.getByRole("button", { name: "Try again" }).click();
  expect(onRetry).toHaveBeenCalledOnce();
});

for (const [error, said] of [
  ["ModelHTTPError: status_code: 529, model_name: claude, body: overloaded", "overloaded"],
  ["status_code: 429, rate limit exceeded", "limiting requests"],
  ["ReadTimeout: the request timed out", "didn't answer in time"],
] as const) {
  test(`a provider's error is said in words, its text under Details: ${said}`, async () => {
    const screen = await render(
      <Messages>
        <RunFailed reason={null} error={error} />
      </Messages>,
    );
    const note = screen.getByRole("note").element();
    expect(note.querySelector("p")?.textContent).toContain(said);
    await expect.element(screen.getByText(error)).not.toBeVisible();
    expect(screen.getByText("Details").elements()).toHaveLength(1);
  });
}

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

test("no sentence claims that nothing was lost, and a tool's timeout isn't blamed on the model", async () => {
  const screen = await render(
    <Messages>
      <RunFailed reason={null} error="ToolError: the tool fetch_page timed out" />
      <RunFailed reason={null} error="status_code: 529, overloaded" />
    </Messages>,
  );
  const said = screen
    .getByRole("note")
    .elements()
    .map((note) => note.querySelector("p")?.textContent);
  expect(said[0]).toContain("Something went wrong before it answered.");
  expect(said.join(" ")).not.toContain("Nothing was lost");
});
