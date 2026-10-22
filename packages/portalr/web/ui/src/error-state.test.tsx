import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { EmptyState } from "./empty-state";
import { ErrorState } from "./error-state";

test("an error state says what couldn't be read, the failure, and reading it again; it takes the focus", async () => {
  const retry = vi.fn();
  const screen = await render(
    <ErrorState
      title="The audit log couldn't be read"
      error={new Error("the server is down")}
      retry={retry}
    />,
  );
  const heading = screen.getByRole("heading", { name: "The audit log couldn't be read" });
  await expect.element(heading).toHaveFocus();
  await expect.element(screen.getByRole("alert")).toHaveTextContent("The server is down");
  await screen.getByRole("button", { name: "Try again" }).click();
  expect(retry).toHaveBeenCalledOnce();
});

test("an empty state takes the focus only when it stands in for the page", async () => {
  const screen = await render(
    <>
      <EmptyState title="No artifacts yet">Nothing here.</EmptyState>
      <EmptyState focus title="Artifact not found">
        Not here.
      </EmptyState>
    </>,
  );
  await expect.element(screen.getByRole("heading", { name: "Artifact not found" })).toHaveFocus();
  const quiet = screen.getByRole("heading", { name: "No artifacts yet" }).element();
  expect(quiet.hasAttribute("tabindex")).toBe(false);
});
