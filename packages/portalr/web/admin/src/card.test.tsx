import { Refused } from "@portalr/client";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Guarded, SaidCard } from "./card";
import { spendSaid } from "./home";

test("a spend near its budget shows the badge: a word and a shape", async () => {
  const said = spendSaid({
    status: "ok",
    data: { spend: 85, max_budget: 100, budget_duration: "30d" },
  });
  const screen = await render(<SaidCard title="Spend" said={said} />);
  const card = screen.getByRole("article", { name: "Spend" });
  await expect.element(card.getByText("Near budget")).toBeVisible();
  await expect.element(card.getByText("$85.00")).toBeVisible();
  await expect.element(card.getByText("of $100.00, every 30 days")).toBeVisible();
});

function Throws({ error }: { error: Error }): null {
  throw error;
}

test("a card refused for the reader is hidden; one that failed says so", async () => {
  const screen = await render(
    <>
      <Guarded title="Members">
        <Throws error={new Refused(403, { detail: { type: "forbidden" } })} />
      </Guarded>
      <Guarded title="Spend">
        <Throws error={new Error("down")} />
      </Guarded>
    </>,
  );
  await expect.element(screen.getByRole("article", { name: "Members" })).not.toBeInTheDocument();
  const spend = screen.getByRole("article", { name: "Spend" });
  await expect.element(spend.getByText("Failed")).toBeVisible();
  await expect.element(spend.getByText("This couldn't be read.")).toBeVisible();
});

test("a card being read is busy, and says so", async () => {
  const never = new Promise<never>(() => undefined);
  function Reading(): null {
    throw never;
  }
  const screen = await render(
    <Guarded title="Feedback">
      <Reading />
    </Guarded>,
  );
  await expect
    .element(screen.getByRole("article", { name: "Feedback" }))
    .toHaveAttribute("aria-busy", "true");
});
