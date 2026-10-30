import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ASKING } from "./states";
import { token } from "./test/colours";

/** A system colour as the browser resolves it now, read off a probe that keeps its own. */
function systemColour(name: string): string {
  const probe = document.createElement("span");
  probe.style.cssText = `background: ${name}; forced-color-adjust: none`;
  document.body.append(probe);
  const colour = getComputedStyle(probe).backgroundColor;
  probe.remove();
  return colour;
}

test("the asking tick is the working colour, and under forced colours the system's highlight", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const screen = await render(<div className={ASKING}>Which week?</div>);
  const card = screen.getByText("Which week?").element();
  const tick = () => getComputedStyle(card, "::before");
  expect(tick().backgroundColor).toBe(token("accent"));
  await commands.forcedColors(true);
  await expect.poll(() => matchMedia("(forced-colors: active)").matches).toBe(true);
  // Its own colour kept, so the system doesn't take it away with the page's.
  expect(tick().forcedColorAdjust).toBe("none");
  expect(tick().backgroundColor).toBe(systemColour("Highlight"));
});
