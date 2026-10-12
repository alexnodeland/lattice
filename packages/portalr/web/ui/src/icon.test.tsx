import { Plus } from "lucide-react";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { Icon } from "./icon";

test("an icon is hidden, so the word beside it names the control", async () => {
  const screen = await render(
    <Button>
      <Icon icon={Plus} />
      New thread
    </Button>,
  );
  const button = screen.getByRole("button", { name: "New thread" }).element();
  const svg = button.querySelector("svg");
  expect(svg?.getAttribute("aria-hidden")).toBe("true");
  expect(svg?.getAttribute("focusable")).toBe("false");
});
