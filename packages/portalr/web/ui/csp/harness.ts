/**
 * A page on the CSP tests' harness, and what it has reported: each violation of the policy, each
 * use of WebAssembly, and each error. The policy allows first-party WebAssembly (portalr ADR-0041),
 * so it can't refuse a module here; the page reports each call that compiles one instead, since
 * Markdown, its add-ons and a dashboard need none. With `search`, the page draws what it names at load, from a task of its own, which a
 * test's `page.evaluate` isn't: Playwright runs that outside the page's `script-src` check, so an
 * `eval` there passes where the page's own would be refused (portalr ADR-0047).
 */

import type { Browser, Page } from "playwright";
import { inject } from "vitest";

/** What compiles or instantiates WebAssembly: a page that calls one of these uses it. */
const COMPILING = ["compile", "compileStreaming", "instantiate", "instantiateStreaming", "Module"];

export async function open(
  browser: Browser,
  search = "",
): Promise<{ page: Page; reported: () => Promise<string[]> }> {
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
  const reported = async () => {
    // A violation is reported as a task of its own, after what caused it.
    await page.evaluate(() => new Promise((settled) => setTimeout(settled, 50)));
    const violations = await page.evaluate(
      () => (window as unknown as { violations: string[] }).violations,
    );
    return [...violations, ...errors];
  };
  return { page, reported };
}
