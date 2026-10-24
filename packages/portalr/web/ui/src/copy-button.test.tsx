import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { CopyButton } from "./copy-button";

test("a copy says what it did in its own status, or, given onSaid, hands it to its page's", async () => {
  vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  const alone = await render(<CopyButton text="abc" what="the id" />);
  await alone.getByRole("button", { name: "Copy the id" }).click();
  await expect.element(alone.getByRole("status")).toHaveTextContent("Copied the id");
  await alone.unmount();
  const said = vi.fn();
  const shared = await render(<CopyButton text="abc" what="trace c029eec0" onSaid={said} />);
  expect(shared.getByRole("status").elements()).toHaveLength(0);
  await shared.getByRole("button", { name: "Copy trace c029eec0" }).click();
  await expect.poll(() => said.mock.calls).toEqual([["Copied trace c029eec0"]]);
  vi.restoreAllMocks();
});
