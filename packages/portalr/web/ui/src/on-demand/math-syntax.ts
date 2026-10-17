/**
 * Math's syntax, loaded with the first message that holds a `$$` (portalr ADR-0044): `$$…$$` within
 * a line, and a block between lines of `$$`. A single `$` is a price, never math. Each becomes code
 * in the language `math`, which `Markdown` draws, or shows as its source while math is off.
 */

import remarkMath from "remark-math";
import type { MathPlugin } from "streamdown";

export const remarkMathSyntax: MathPlugin["remarkPlugin"] = [
  remarkMath,
  { singleDollarTextMath: false },
];
