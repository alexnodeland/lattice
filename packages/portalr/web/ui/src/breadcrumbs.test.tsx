import { expect, onTestFinished, test } from "vitest";
import { page } from "vitest/browser";
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

test("one crumb has no separator", async () => {
  const screen = await render(<Breadcrumbs trail={[{ label: "Rules", href: "#rules" }]} />);
  expect(screen.container.textContent).toBe("Rules");
});

test("the separators between crumbs are hidden from assistive technology", async () => {
  const screen = await render(
    <Breadcrumbs
      trail={[
        { label: "Workspace", href: "#notes" },
        { label: "Threads", href: "#threads" },
      ]}
    />,
  );
  expect(screen.getByText("/").element().getAttribute("aria-hidden")).toBe("true");
});

test("an empty trail shows nothing", async () => {
  const screen = await render(<Breadcrumbs trail={[]} />);
  expect(screen.container.querySelector("nav")).toBeNull();
});

test("on a phone, a crumb is still a target 24px tall", async () => {
  await page.viewport(390, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<Breadcrumbs trail={[{ label: "Threads", href: "#threads" }]} />);
  const link = screen.getByRole("link", { name: "Threads" }).element();
  expect(link.getBoundingClientRect().height).toBeGreaterThanOrEqual(24);
});

test("a crumb is followed when clicked", async () => {
  onTestFinished(() => history.replaceState(null, "", location.pathname + location.search));
  const screen = await render(<Breadcrumbs trail={[{ label: "Traces", href: "#traces" }]} />);
  await screen.getByRole("link", { name: "Traces" }).click();
  expect(location.hash).toBe("#traces");
});
