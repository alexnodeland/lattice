/**
 * SPDX licence expressions, as package.json's `license` field holds them: `MIT`, `MIT AND ISC`,
 * `(MIT OR Apache-2.0)`, `Apache-2.0 WITH LLVM-exception`, `GPL-2.0+`. Whether one is allowed is
 * decided by the licences in it and how they combine: `AND` needs both sides allowed, `OR` either,
 * and `WITH` never is, since an exception changes what a licence grants.
 */

export type Expression =
  | { readonly kind: "id"; readonly id: string; readonly exception?: string }
  | { readonly kind: "and" | "or"; readonly left: Expression; readonly right: Expression };

const TOKEN = /\s*(\(|\)|[A-Za-z0-9.+-]+)/y;

function tokens(text: string): string[] | undefined {
  const found: string[] = [];
  TOKEN.lastIndex = 0;
  while (TOKEN.lastIndex < text.length) {
    const match = TOKEN.exec(text);
    if (match?.[1] === undefined) {
      return text.slice(TOKEN.lastIndex).trim() === "" ? found : undefined;
    }
    found.push(match[1]);
  }
  return found;
}

/** The expression `text` spells, or undefined where it isn't valid SPDX (`SEE LICENSE IN …`). */
export function parse(text: string): Expression | undefined {
  const words = tokens(text);
  if (words === undefined || words.length === 0) {
    return undefined;
  }
  let position = 0;
  const peek = () => words[position];
  const isOperator = (word: string | undefined) =>
    word === "AND" || word === "OR" || word === "WITH";
  const isId = (word: string | undefined): word is string =>
    word !== undefined && word !== "(" && word !== ")" && !isOperator(word);

  function term(): Expression | undefined {
    const word = peek();
    if (word === "(") {
      position += 1;
      const inner = or();
      if (inner === undefined || peek() !== ")") {
        return undefined;
      }
      position += 1;
      return inner;
    }
    if (!isId(word)) {
      return undefined;
    }
    position += 1;
    if (peek() === "WITH") {
      position += 1;
      const exception = peek();
      if (!isId(exception)) {
        return undefined;
      }
      position += 1;
      return { kind: "id", id: word, exception };
    }
    return { kind: "id", id: word };
  }

  function and(): Expression | undefined {
    let left = term();
    while (left !== undefined && peek() === "AND") {
      position += 1;
      const right = term();
      left = right === undefined ? undefined : { kind: "and", left, right };
    }
    return left;
  }

  function or(): Expression | undefined {
    let left = and();
    while (left !== undefined && peek() === "OR") {
      position += 1;
      const right = and();
      left = right === undefined ? undefined : { kind: "or", left, right };
    }
    return left;
  }

  const expression = or();
  return position === words.length ? expression : undefined;
}

/** Whether every way of satisfying the expression is within `allowed` (compared without case). */
export function allows(expression: Expression, allowed: ReadonlySet<string>): boolean {
  if (expression.kind === "id") {
    // "X+" is X or a later version: allowed when X is. A licence with an exception never is.
    return (
      expression.exception === undefined &&
      allowed.has(expression.id.replace(/\+$/, "").toLowerCase())
    );
  }
  const left = allows(expression.left, allowed);
  const right = allows(expression.right, allowed);
  return expression.kind === "and" ? left && right : left || right;
}
