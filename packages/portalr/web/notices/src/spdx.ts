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

/** The identifiers in the expression, as written (`GPL-2.0+` is `GPL-2.0`), in order. */
export function ids(expression: Expression): string[] {
  return expression.kind === "id"
    ? [expression.id.replace(/\+$/, "")]
    : [...ids(expression.left), ...ids(expression.right)];
}

/** Whether the expression offers a choice: it has an OR in it. */
export function offersChoice(expression: Expression): boolean {
  return (
    expression.kind === "or" ||
    (expression.kind === "and" && (offersChoice(expression.left) || offersChoice(expression.right)))
  );
}

/**
 * The licences the package is used under, where it is allowed: an `AND` needs both sides, and an
 * `OR` is elected to its first allowed alternative, as SPDX has the one who uses it choose.
 * Undefined where no way of satisfying it is allowed.
 */
export function elect(expression: Expression, allowed: ReadonlySet<string>): string[] | undefined {
  if (expression.kind === "id") {
    return allows(expression, allowed) ? [expression.id.replace(/\+$/, "")] : undefined;
  }
  const left = elect(expression.left, allowed);
  if (expression.kind === "or") {
    return left ?? elect(expression.right, allowed);
  }
  const right = elect(expression.right, allowed);
  return left === undefined || right === undefined ? undefined : [...left, ...right];
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
