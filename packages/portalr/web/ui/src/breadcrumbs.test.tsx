import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Breadcrumbs } from "./breadcrumbs";
import { token } from "./test/colours";

test("the way back is a navigation named Breadcrumb, outermost first", async () => {
  const screen = await render(
    <Breadcrumbs
      trail={[
        { label: "Workspace", href: "#notes" },
        { label: "Threads", href: "#threads" },
      ]}
    />,
  );
  const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
  await expect.element(nav).toBeVisible();
  const links = nav.getByRole("link").elements();
  expect(links.map((link) => link.textContent)).toEqual(["Workspace", "Threads"]);
});

test("a crumb is a target 24px tall or more, in the quiet link's look", async () => {
  const screen = await render(<Breadcrumbs trail={[{ label: "Rules", href: "#rules" }]} />);
  const link = screen.getByRole("link", { name: "Rules" }).element();
  expect(link.getBoundingClientRect().height).toBeGreaterThanOrEqual(24);
  expect(getComputedStyle(link).color).toBe(token("fg"));
});

test("a router's link renders a crumb", async () => {
  const screen = await render(
    <Breadcrumbs
      trail={[
        {
          label: "Traces",
          render: (
            <a data-router="yes" href="#traces">
              Traces
            </a>
          ),
        },
      ]}
    />,
  );
  const link = screen.getByRole("link", { name: "Traces" }).element();
  expect(link.getAttribute("data-router")).toBe("yes");
});
