/**
 * A JSON Patch (RFC 6902) applied to a copy of an artifact's data, as artifactr applies an edit's:
 * what a proposed edit would make, to show beside what it was made against. A patch that doesn't
 * apply gives null, and the proposal is shown without it. It applies the ops artifactr's `diff`
 * writes (Python jsonpatch's `make_patch`: add, remove, replace and move); any other op doesn't
 * apply.
 */

type Json = unknown;
type Container = Record<string, Json> | Json[];

const isContainer = (value: Json): value is Container =>
  typeof value === "object" && value !== null;

/** A pointer's tokens, `~1` and `~0` read as `/` and `~`. */
const tokens = (pointer: string): string[] | null =>
  pointer === ""
    ? []
    : pointer.startsWith("/")
      ? pointer
          .slice(1)
          .split("/")
          .map((token) => token.replaceAll("~1", "/").replaceAll("~0", "~"))
      : null;

/** The container a pointer's last token is in, and that token; null where there is none. */
function parent(root: Json, pointer: string): [Container, string] | null {
  const path = tokens(pointer);
  const last = path?.pop();
  if (path === null || path === undefined || last === undefined) {
    return null;
  }
  let at: Json = root;
  for (const token of path) {
    if (!isContainer(at) || !Object.hasOwn(at, token)) {
      return null;
    }
    at = (at as Record<string, Json>)[token];
  }
  return isContainer(at) ? [at, last] : null;
}

function remove(root: Json, pointer: string): Json | undefined {
  const found = parent(root, pointer);
  if (found === null) {
    return undefined;
  }
  const [at, key] = found;
  if (!Object.hasOwn(at, key)) {
    return undefined;
  }
  const was = (at as Record<string, Json>)[key];
  if (Array.isArray(at)) {
    at.splice(Number(key), 1);
  } else {
    delete at[key];
  }
  return was;
}

function add(root: Json, pointer: string, value: Json): boolean {
  const found = parent(root, pointer);
  if (found === null) {
    return false;
  }
  const [at, key] = found;
  if (Array.isArray(at)) {
    const index = key === "-" ? at.length : Number(key);
    if (!Number.isInteger(index) || index < 0 || index > at.length) {
      return false;
    }
    at.splice(index, 0, value);
  } else {
    at[key] = value;
  }
  return true;
}

/** `data` with `ops` applied, as a copy; null where an op doesn't apply. */
export function applyPatch(
  data: Readonly<Record<string, unknown>>,
  ops: readonly Readonly<Record<string, unknown>>[],
): Record<string, unknown> | null {
  const root: Json = structuredClone(data);
  for (const op of ops) {
    const path = typeof op.path === "string" ? op.path : null;
    const from = typeof op.from === "string" ? op.from : null;
    if (path === null || path === "") {
      return null;
    }
    const ok = (() => {
      switch (op.op) {
        case "add":
          return add(root, path, structuredClone(op.value));
        case "remove":
          return remove(root, path) !== undefined;
        case "replace":
          return remove(root, path) !== undefined && add(root, path, structuredClone(op.value));
        case "move": {
          const moved = from === null ? undefined : remove(root, from);
          return moved !== undefined && add(root, path, moved);
        }
        default:
          return false;
      }
    })();
    if (!ok) {
      return null;
    }
  }
  return root as Record<string, unknown>;
}
