/**
 * A reflexr rule in words, stage by stage, in the order reflexr runs them (portalr ADR-0017): the
 * event types it is on, the filter, the pattern, dedupe and throttle, the scope, the action, and
 * how it retries; any other setting it holds, such as `start`, as itself. Each stage is lines, nested as `all`, `any` and `not` nest; a part of a
 * shape it doesn't know is its JSON, in its place, so a newer rule still reads. The rule's shape is
 * reflexr's schema's, generated; it is read here defensively, since a draft is data.
 */

import type { ReflexrRulesV1 as R } from "@portalr/client";
import { isObject } from "./json";

/** A line of a stage: what it says, as words or, for a part not known here, as JSON. */
export interface Line {
  readonly said: string;
  /** What it says is JSON: a part of a shape not known here, shown as it is. */
  readonly json?: boolean;
  /** A field's name, as an action's params are said: `to` beside its value. */
  readonly term?: string;
  /** It follows another that must hold too: said "and". */
  readonly and?: boolean;
  /** What it holds, said beneath it: an `all`'s filters, a sequence's steps. */
  readonly of?: readonly Line[];
}

/** A stage of the pipeline, by name, and what it says. */
export interface Stage {
  readonly name: string;
  readonly lines: readonly Line[];
  /** It says nothing of its own, as a rule without a throttle: shown quieter. */
  readonly none?: boolean;
}

type Obj = Readonly<Record<string, unknown>>;

const json = (value: unknown): Line => ({ said: JSON.stringify(value) ?? "null", json: true });

/** The units of a duration, in the order ISO 8601 writes them. */
const UNITS = ["year", "month", "week", "day", "hour", "minute", "second"];

/** A list in words: "a, b and c", or "a, b or c". */
const listed = (items: readonly string[], last: string) =>
  items.length < 2 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} ${last} ${items.at(-1)}`;

const ISO =
  /^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$/;

/** An ISO 8601 duration in words, "1 hour and 30 minutes"; one it can't read, as written. */
export function duration(value: unknown): string {
  const found = typeof value === "string" ? ISO.exec(value) : null;
  if (found === null || value === "P" || value === "PT") {
    return typeof value === "string" ? value : JSON.stringify(value);
  }
  const words = UNITS.flatMap((unit, at) => {
    const n = found[at + 1];
    return n === undefined || Number(n) === 0 ? [] : [`${n} ${unit}${n === "1" ? "" : "s"}`];
  });
  return words.length === 0 ? "no time" : listed(words, "and");
}

const OPS: Record<R.Op, string> = {
  eq: "=",
  ne: "≠",
  lt: "<",
  le: "≤",
  gt: ">",
  ge: "≥",
  in: "is one of",
  contains: "contains",
  matches: "matches",
  exists: "exists",
};

const value = (v: unknown) => JSON.stringify(v) ?? "null";

/** A list in words: "a, b or c". */
const strings = (v: unknown): v is readonly string[] =>
  Array.isArray(v) && v.length > 0 && v.every((each) => typeof each === "string");

/** A filter, as lines: a comparison as a sentence, and `all`, `any` and `not` as nesting. */
export function filterLine(filter: unknown): Line {
  if (!isObject(filter)) {
    return json(filter);
  }
  const f = filter as Obj & { kind?: unknown };
  switch (f.kind) {
    case "on":
      return strings(f.types) ? { said: `the event is ${listed(f.types, "or")}` } : json(filter);
    case "where": {
      const { field, op } = f as Partial<R.WhereFilter>;
      if (typeof field !== "string" || typeof op !== "string" || !(op in OPS)) {
        return json(filter);
      }
      if (op === "exists") {
        return { said: f.value === false ? `${field} is missing` : `${field} exists` };
      }
      if (op === "in" && Array.isArray(f.value)) {
        return { said: `${field} is one of ${f.value.map(value).join(", ")}` };
      }
      return { said: `${field} ${OPS[op]} ${value(f.value)}` };
    }
    case "all":
    case "any":
      return Array.isArray(f.of) && f.of.length > 0
        ? { said: f.kind === "all" ? "all of" : "any of", of: f.of.map(filterLine) }
        : json(filter);
    case "not":
      return "filter" in f ? { said: "not", of: [filterLine(f.filter)] } : json(filter);
    case "predicate":
      return typeof f.name === "string" ? { said: `passes ${f.name}` } : json(filter);
    default:
      return json(filter);
  }
}

/** The event types a filter is on, at its top, and the rest of it. */
function split(filter: unknown): { types: readonly string[]; rest: readonly unknown[] } {
  const on = (each: unknown): each is R.OnFilter =>
    isObject(each) && each.kind === "on" && strings(each.types);
  if (on(filter)) {
    return { types: filter.types, rest: [] };
  }
  // One `on` beside other filters gives the event types; several are each a filter, which must
  // all hold, as reflexr reads `all`.
  if (isObject(filter) && filter.kind === "all" && Array.isArray(filter.of)) {
    const of: readonly unknown[] = filter.of;
    const ons = of.filter(on);
    if (ons.length === 1 && ons[0]) {
      return { types: ons[0].types, rest: of.filter((e) => !on(e)) };
    }
  }
  return { types: [], rest: filter === undefined ? [] : [filter] };
}

function patternLines(pattern: unknown): readonly Line[] {
  if (pattern === undefined) {
    return [{ said: "each event" }];
  }
  if (!isObject(pattern)) {
    return [json(pattern)];
  }
  const p = pattern as Obj;
  switch (p.kind) {
    case "each":
      return [{ said: "each event" }];
    case "count":
      return typeof p.at_least === "number"
        ? [
            {
              said: `fires when ${p.at_least} arrive within ${duration(p.within)}, then starts over`,
            },
          ]
        : [json(pattern)];
    case "sequence":
      return Array.isArray(p.steps)
        ? [{ said: `these, in order, within ${duration(p.within)}`, of: p.steps.map(filterLine) }]
        : [json(pattern)];
    case "absence":
      return [{ said: `quiet for ${duration(p.within)}, per scope seen` }];
    default:
      return [json(pattern)];
  }
}

/** A part's lines where it may be absent: what it says, or `none` where it is. */
function optional(part: unknown, say: (part: Obj) => string | null, name: string): Stage {
  if (part === undefined || part === null) {
    return { name, lines: [{ said: "none" }], none: true };
  }
  const said = typeof part === "string" ? duration(part) : isObject(part) ? say(part) : null;
  return { name, lines: [said === null ? json(part) : { said }] };
}

/** What of `object` isn't one of `known`, as JSON lines named by their keys. */
const unknown = (object: Obj, known: readonly string[], under = ""): Line[] =>
  Object.entries(object)
    .filter(([key]) => !known.includes(key))
    .map(([key, v]) => ({ ...json(v), term: `${under}${key}` }));

/** A rule's keys the stages say; any other the rule holds, such as `start` or `ordering`, is said as itself, under more. */
const RULE = ["name", "description", "enabled", "when", "then", "scope", "retry", "timeout"];
const WHEN = ["filter", "pattern", "dedupe", "throttle"];
const THEN = ["action", "params"];
const RETRY = ["max_attempts", "backoff", "multiplier", "max_backoff"];

/** How a rule retries, its defaults reflexr's: up to 5 attempts, 1 second apart, doubling, at most 5 minutes. */
function retries(retry: unknown): Stage {
  if (retry !== undefined && !isObject(retry)) {
    return { name: "retries", lines: [json(retry)] };
  }
  const r: Partial<R.RetryPolicy> = retry ?? {};
  const attempts = r.max_attempts ?? 5;
  const said =
    attempts === 1
      ? "1 attempt, no retries"
      : `up to ${attempts} attempts, ${duration(r.backoff ?? "PT1S")} apart, ×${r.multiplier ?? 2} each time, at most ${duration(r.max_backoff ?? "PT5M")} apart`;
  return { name: "retries", lines: [{ said }, ...(isObject(retry) ? unknown(retry, RETRY) : [])] };
}

/** A rule's stages, in the order reflexr runs them, each always there, so a change reads as one. */
export function stages(rule: Obj): readonly Stage[] {
  const when: Obj = isObject(rule.when) ? rule.when : {};
  const then: Obj = isObject(rule.then) ? rule.then : {};
  const { types, rest } = split(when.filter);
  // Beside the event types, each filter must hold: the second on say so.
  const filter = rest.map((each, at) => {
    const line = filterLine(each);
    return at === 0 ? line : { ...line, and: true };
  });
  const scope = isObject(rule.scope) ? rule.scope.fields : [];
  const params = isObject(then.params) ? Object.entries(then.params) : [];
  return [
    // Whether it runs, said only where it doesn't, and what it is for, where it says.
    ...(rule.enabled === undefined || rule.enabled === true
      ? []
      : [
          {
            name: "status",
            lines: [rule.enabled === false ? { said: "disabled" } : json(rule.enabled)],
          },
        ]),
    ...(rule.description === undefined || rule.description === ""
      ? []
      : [
          {
            name: "description",
            lines: [
              typeof rule.description === "string"
                ? { said: rule.description }
                : json(rule.description),
            ],
          },
        ]),
    {
      name: "event types",
      lines:
        types.length > 0 ? types.map((said) => ({ said, json: true })) : [{ said: "any event" }],
      none: types.length === 0,
    },
    filter.length > 0 ? { name: "filter", lines: filter } : optional(null, () => null, "filter"),
    { name: "pattern", lines: patternLines(when.pattern) },
    optional(
      when.dedupe,
      (d) =>
        strings(d.key)
          ? `once per ${d.key.join(", ")} within ${duration(d.within)}, per scope`
          : null,
      "dedupe",
    ),
    optional(
      when.throttle,
      (t) =>
        typeof t.at_most === "number"
          ? `at most ${t.at_most} per ${duration(t.per)}, per scope`
          : null,
      "throttle",
    ),
    rule.scope === undefined || (Array.isArray(scope) && scope.length === 0)
      ? { name: "scope", lines: [{ said: "one scope" }] }
      : strings(scope)
        ? { name: "scope", lines: [{ said: `per ${scope.join(", ")}` }] }
        : { name: "scope", lines: [json(rule.scope)] },
    {
      name: "action",
      lines: [
        typeof then.action === "string" ? { said: then.action } : json(rule.then),
        ...params.map(([term, v]) => ({ ...json(v), term })),
        ...(then.params !== undefined && !isObject(then.params)
          ? [{ ...json(then.params), term: "params" }]
          : []),
        ...unknown(then, THEN),
      ],
    },
    retries(rule.retry),
    optional(rule.timeout, () => null, "timeout"),
    ...((): Stage[] => {
      const more = [...unknown(rule, RULE), ...unknown(when, WHEN, "when.")];
      return more.length > 0 ? [{ name: "more", lines: more }] : [];
    })(),
  ];
}

/** A stage's lines as text, nested lines indented, a field as `name: value`. */
export function stageText(lines: readonly Line[], depth = 0): string {
  return lines
    .map((line) => {
      const head = `${"  ".repeat(depth)}${line.and ? "and " : ""}${line.term === undefined ? "" : `${line.term}: `}${line.said}`;
      return line.of ? `${head}\n${stageText(line.of, depth + 1)}` : head;
    })
    .join("\n");
}
