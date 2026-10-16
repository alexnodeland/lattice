import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Num } from "./num";

/** The width, in px, of a figure as `Num` sets it, in the page's sans face. */
async function widthOf(text: string, set?: string): Promise<number> {
  await document.fonts.load('1em "Schibsted Grotesk"');
  const screen = await render(
    <span data-testid="figure" className="whitespace-pre text-4xl">
      {set === undefined ? <Num>{text}</Num> : <span className={set}>{text}</span>}
    </span>,
  );
  const { width } = screen.getByTestId("figure").element().getBoundingClientRect();
  await screen.unmount();
  return width;
}

test("a figure's decimal point keeps its own width, so $60.40 is not set as $60 . 40", async () => {
  const withPoint = await widthOf("6040");
  const withDecimals = await widthOf("60.40");
  // The digits are the same; what is added is a point, narrower than any one digit.
  expect(withDecimals - withPoint).toBeGreaterThan(0);
  expect(withDecimals - withPoint).toBeLessThan(withPoint / 5);
});

test("the face's tabular set changes the decimal point, comma, colon and percent sign, and Num leaves them", async () => {
  for (const mark of [".", ",", ":", "%"]) {
    const tabular = await widthOf(mark, "tabular-nums");
    const plain = await widthOf(mark, "");
    expect(tabular, `${mark} in the tabular set`).not.toBeCloseTo(plain, 0);
    // Alone, a mark has no digit run, so Num sets it as the face does by default.
    expect(await widthOf(mark), mark).toBeCloseTo(plain, 1);
  }
});

test("figures with as many digits are as wide, so a column of them lines up", async () => {
  expect(await widthOf("1,111.11")).toBeCloseTo(await widthOf("8,888.88"), 1);
});

test("only the digits are tabular", async () => {
  const screen = await render(<Num>{"$1,250.50 · 40%"}</Num>);
  const tabular = [...screen.container.querySelectorAll(".tabular-nums")].map((e) => e.textContent);
  expect(tabular).toEqual(["1", "250", "50", "40"]);
  expect(screen.container.textContent).toBe("$1,250.50 · 40%");
});
