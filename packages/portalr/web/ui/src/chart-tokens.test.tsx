import { useRef } from "react";
import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { render } from "vitest-browser-react";
import { useChartTokens } from "./chart-tokens";
import { token } from "./test/colours";

function Tokens({ wanted = true }: { wanted?: boolean }) {
  const within = useRef<HTMLDivElement>(null);
  const tokens = useChartTokens(within, wanted);
  return (
    <div ref={within}>
      <output>
        {tokens === null
          ? "unread"
          : `${tokens.colours["chart-1"]}|${tokens.colours.muted}|${tokens.cvd}|${tokens.forced}`}
      </output>
    </div>
  );
}

test("the chart's colours are the tokens, as the browser draws them in this scheme", async () => {
  const screen = await render(<Tokens />);
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(`${token("chart-1")}|${token("muted")}|false|false`);
});

test("they are read again when colour-blind mode or forced colours change", async () => {
  onTestFinished(() => {
    delete document.documentElement.dataset.cvd;
  });
  onTestFinished(() => commands.forcedColors(false));
  const screen = await render(<Tokens />);
  const plain = token("chart-1");
  document.documentElement.dataset.cvd = "";
  const blind = token("chart-1");
  expect(blind).not.toBe(plain);
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(`${blind}|${token("muted")}|true|false`);
  delete document.documentElement.dataset.cvd;
  await commands.forcedColors(true);
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(`${token("chart-1")}|${token("muted")}|false|true`);
});

test("they are read again when the page's scheme is chosen", async () => {
  onTestFinished(() => {
    delete document.documentElement.dataset.theme;
  });
  const screen = await render(<Tokens />);
  const other = document.documentElement.dataset;
  other.theme = matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark";
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent(`${token("chart-1")}|${token("muted")}|false|false`);
});

test("they follow colour-blind mode set on an element round the chart, not the root", async () => {
  const screen = await render(
    <div data-testid="round">
      <Tokens />
    </div>,
  );
  const round = screen.getByTestId("round").element() as HTMLElement;
  round.dataset.cvd = "";
  await expect
    .poll(() => screen.getByRole("status").element().textContent)
    .toMatch(/\|true\|false$/);
});

test("where nothing wants them, they aren't read", async () => {
  const screen = await render(<Tokens wanted={false} />);
  await expect.element(screen.getByRole("status")).toHaveTextContent("unread");
});
