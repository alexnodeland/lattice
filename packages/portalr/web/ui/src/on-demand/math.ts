/**
 * Math, drawn by KaTeX as MathML, which the browser lays out itself, so no stylesheet or face comes
 * with it: Streamdown's math plugin, of `ui`'s own, loaded with the first formula a page draws while
 * math is on (portalr ADR-0044). Its rehype step runs after the sanitizer, so what it adds is safe
 * by construction: KaTeX's MathML for TeX read with `trust: false`.
 */

import type { Element, ElementContent, Root, RootContent } from "hast";
import { fromHtmlIsomorphic } from "hast-util-from-html-isomorphic";
import katex, { type KatexOptions } from "katex";
import type { MathPlugin } from "streamdown";
import { SCROLLS } from "../scroll-region";
import { remarkMathSyntax } from "./math-syntax";

/**
 * Untrusted TeX, read safely: no `\href`, `\url`, `\includegraphics` or `\html…` (`trust: false`),
 * bounded in size and in macro expansion, and refused, rather than drawn as KaTeX's red error,
 * whose inline style the Content-Security-Policy would refuse.
 */
const OPTIONS: KatexOptions = {
  output: "mathml",
  trust: false,
  throwOnError: true,
  strict: "ignore",
  maxSize: 20,
  maxExpand: 1000,
};

/** The longest formula drawn; a longer one shows as its source. */
const LONGEST = 5000;

/**
 * KaTeX writes a `style` attribute for `\fcolorbox`'s border and `\pmb`'s shadow alone, which the
 * policy refuses: they are dropped, and the formula drawn without them. KaTeX escapes every value
 * and every text, so this matches its attributes alone.
 */
const STYLE = /\sstyle="[^"]*"/g;

/** A formula's MathML as hast, or nothing for TeX that isn't a formula KaTeX draws. */
function drawn(tex: string, display: boolean): ElementContent[] | null {
  if (tex.length > LONGEST) {
    return null;
  }
  try {
    const html = katex.renderToString(tex, { ...OPTIONS, displayMode: display });
    return fromHtmlIsomorphic(html.replace(STYLE, ""), { fragment: true })
      .children as ElementContent[];
  } catch {
    return null;
  }
}

const isMath = (node: RootContent | ElementContent): node is Element =>
  node.type === "element" &&
  node.tagName === "code" &&
  Array.isArray(node.properties.className) &&
  node.properties.className.includes("language-math");

const texOf = (code: Element) =>
  code.children.map((child) => (child.type === "text" ? child.value : "")).join("");

/**
 * Each formula, drawn where it stands: a block (`pre > code.language-math`) in a region that
 * scrolls sideways, and one within a line in place. One KaTeX can't read stays as its code, which
 * `Markdown` shows as its source.
 */
function draw(parent: Root | Element): void {
  parent.children = parent.children.flatMap((child): (RootContent & ElementContent)[] => {
    if (child.type !== "element") {
      return [child as RootContent & ElementContent];
    }
    const code = child.tagName === "pre" ? child.children.find(isMath) : undefined;
    if (code || isMath(child)) {
      const block = code !== undefined;
      const math = drawn(texOf(code ?? child), block);
      if (math) {
        return block
          ? [
              {
                type: "element",
                tagName: "section",
                properties: { ariaLabel: "Formula", tabIndex: 0, className: [SCROLLS, "py-1"] },
                children: math,
              },
            ]
          : math;
      }
      return [child];
    }
    draw(child);
    return [child];
  });
}

/** Streamdown's math plugin: remark-math's syntax, and this drawing of it. */
const MATH: MathPlugin = {
  type: "math",
  name: "katex",
  remarkPlugin: remarkMathSyntax,
  rehypePlugin: () => draw,
};

/** The plugins to give Streamdown while math is on: one object, so its blocks render once again. */
export const PLUGINS = { math: MATH } as const;
