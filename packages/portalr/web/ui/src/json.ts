/** What JSON from the wire is, told apart at run time, as the readers of forms and dashboards ask. */

export const isObject = (value: unknown): value is Readonly<Record<string, unknown>> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const isString = (value: unknown): value is string => typeof value === "string";

/** A number a form or a dashboard holds: finite, and within JavaScript's safe integers either way. */
export const isNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= Number.MAX_SAFE_INTEGER;

/** An object's own value at a key, never one it inherits, such as `constructor`'s. */
export const own = (object: Readonly<Record<string, unknown>>, key: string): unknown =>
  Object.hasOwn(object, key) ? object[key] : undefined;
