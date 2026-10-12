import { renderToStaticMarkup } from "react-dom/server";
import { expect, test } from "vitest";
import { Page } from "./page";

test("a page's title is its heading", () => {
  expect(renderToStaticMarkup(<Page title="portalr">Soon.</Page>)).toBe(
    "<main><h1>portalr</h1>Soon.</main>",
  );
});
