/**
 * A page on the CSP tests' harness, and what it has reported: each violation of the policy, each
 * use of WebAssembly, and each error. The policy refuses WebAssembly (portalr ADR-0041, as
 * artifactr ADR-0088 amends it); the page reports each call that tries to compile a module too,
 * since Markdown, its add-ons and a dashboard need none, and a refused call is otherwise silent.
 * With `search`, the page draws what it names at load, from a task of its own, which a test's
 * `page.evaluate` isn't: Playwright runs that outside the page's `script-src` check, so an `eval`
 * there passes where the page's own would be refused (portalr ADR-0047).
 */

import { type Browser, chromium, type Page } from "playwright";
import { inject } from "vitest";

/** The Chromium the test files share, which `serve.ts` started: closing this disconnects. */
export const connected = (): Promise<Browser> => chromium.connect(inject("chromium"));

/** What compiles or instantiates WebAssembly: a page that calls one of these uses it. */
const COMPILING = ["compile", "compileStreaming", "instantiate", "instantiateStreaming", "Module"];

export async function open(
  browser: Browser,
  search = "",
): Promise<{
  page: Page;
  reported: (atLeast?: number) => Promise<string[]>;
}> {
  // The clipboard is the page's to write, so Copy copies, as it does for a person.
  const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`error: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console: ${message.text()}`);
    }
  });
  // Before the page's own scripts, and whatever its policy: Playwright adds it, not the page.
  await page.addInitScript((compiling) => {
    const seen: string[] = [];
    Object.assign(window, { violations: seen });
    document.addEventListener("securitypolicyviolation", (event) => {
      seen.push(`${event.effectiveDirective}: ${event.blockedURI} at ${event.sourceFile}`);
    });
    // Each call is reported, not each read, so a library that only feature-detects isn't. A
    // worker has a WebAssembly of its own, which this doesn't reach; ui starts none.
    for (const key of compiling) {
      const real = Reflect.get(WebAssembly, key);
      const used = () => seen.push(`WebAssembly.${key}`);
      Reflect.set(
        WebAssembly,
        key,
        new Proxy(real, {
          apply: (target, self, args) => {
            used();
            return Reflect.apply(target, self, args);
          },
          construct: (target, args, newTarget) => {
            used();
            return Reflect.construct(target, args, newTarget);
          },
        }),
      );
    }
  }, COMPILING);
  await page.goto(`${inject("harness")}${search}`);
  /**
   * What the page has reported. A violation is reported as a task of its own, after what caused
   * it, and a loaded runner may take longer than a moment to run it: given `atLeast`, a test that
   * expects reports waits until the page has that many, rather than a fixed while.
   */
  const reported = async (atLeast = 0) => {
    await page.waitForFunction(
      (count) => (window as unknown as { violations: string[] }).violations.length >= count,
      atLeast,
    );
    await page.evaluate(() => new Promise((settled) => setTimeout(settled, 50)));
    const violations = await page.evaluate(
      () => (window as unknown as { violations: string[] }).violations,
    );
    return [...violations, ...errors];
  };
  return { page, reported };
}
