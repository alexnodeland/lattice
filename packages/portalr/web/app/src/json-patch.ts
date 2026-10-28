/**
 * A JSON Patch (RFC 6902) applied to a copy of an artifact's data, as artifactr applies an edit's:
 * what a proposed edit would make, to show beside what it was made against. It applies the ops
 * artifactr's `diff` writes (Python jsonpatch's `make_patch`: add, remove, replace and move). Any
 * other op, a path that doesn't resolve, an array index that isn't one, a key that would reach an
 * object's prototype, or an add or replace without a value, and the patch gives null: the
 * proposal then says it couldn't work out what it changes. It never throws.
 */

type Container = Record<string, unknown> | unknown[];

const isContainer = (value: unknown): value is Container =>
  typeof value === "object" && value !== null;

/** An array's index as RFC 6901 writes one: no sign, no leading zero, no fraction. */
const INDEX = /^(0|[1-9]\d*)$/;

/** Keys that would reach an object's prototype, not a field of it. */
const UNSAFE = new Set(["__proto__", "constructor", "prototype"]);

/** The container a pointer's last token is in, and that token; null where there is none. */
function parent(root: unknown, pointer: string): [Container, string] | null {
  if (!pointer.startsWith("/")) {
    return null;
  }
  const path = pointer
    .slice(1)
    .split("/")
    .map((token) => token.replaceAll("~1", "/").replaceAll("~0", "~"));
  if (path.some((token) => UNSAFE.has(token))) {
    return null;
  }
  const last = path.pop() as string;
  let at = root;
  for (const token of path) {
    if (
      !isContainer(at) ||
      (Array.isArray(at) && !INDEX.test(token)) ||
      !Object.hasOwn(at, token)
    ) {
      return null;
    }
    at = (at as Record<string, unknown>)[token];
  }
  return isContainer(at) ? [at, last] : null;
}

/** What `pointer` held, taken out; undefined where it held nothing. */
function remove(root: unknown, pointer: string): unknown {
  const found = parent(root, pointer);
  if (found === null) {
    return undefined;
  }
  const [at, key] = found;
  if ((Array.isArray(at) && !INDEX.test(key)) || !Object.hasOwn(at, key)) {
    return undefined;
  }
  const was = (at as Record<string, unknown>)[key];
  if (Array.isArray(at)) {
    at.splice(Number(key), 1);
  } else {
    delete at[key];
  }
  return was;
}

function add(root: unknown, pointer: string, value: unknown): boolean {
  const found = parent(root, pointer);
  if (found === null || value === undefined) {
    return false;
  }
  const [at, key] = found;
  if (!Array.isArray(at)) {
    at[key] = value;
    return true;
  }
  const index = key === "-" ? at.length : INDEX.test(key) ? Number(key) : -1;
  if (index < 0 || index > at.length) {
    return false;
  }
  at.splice(index, 0, value);
  return true;
}

/** `data` with `ops` applied, as a copy; null where any op doesn't apply. */
export function applyPatch(data: unknown, ops: unknown): Record<string, unknown> | null {
  try {
    if (!isContainer(data) || !Array.isArray(ops)) {
      return null;
    }
    const [root, list] = structuredClone([data, ops]);
    for (const op of list) {
      if (!isContainer(op) || Array.isArray(op) || typeof op.path !== "string") {
        return null;
      }
      const { path } = op;
      const from = typeof op.from === "string" ? op.from : "";
      const ok =
        op.op === "add"
          ? add(root, path, op.value)
          : op.op === "remove"
            ? remove(root, path) !== undefined
            : op.op === "replace"
              ? op.value !== undefined &&
                remove(root, path) !== undefined &&
                add(root, path, op.value)
              : op.op === "move"
                ? ((moved) => moved !== undefined && add(root, path, moved))(remove(root, from))
                : false;
      if (!ok) {
        return null;
      }
    }
    return root as Record<string, unknown>;
  } catch {
    return null;
  }
}
