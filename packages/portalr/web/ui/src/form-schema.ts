/**
 * A form's schema, read and checked as `SchemaForm` shows it (lattice RFC-0005): which control
 * each property is, in what order and under which section, and what a person's entries are
 * worth as values. The checks are the package's subset's, run before anything is sent so a person
 * sees a refusal at once; the server's check is the one that counts, and its refusal is put under
 * the same fields.
 */

import { INVALID, pathsOf } from "@portalr/client";
import type {
  AskForm,
  Form,
  FormSchema,
  Property,
  PropertyHints,
  RefusalReason,
  UiHints,
  Value,
  Values,
} from "./artifactr-ui";
import { isNumber, isObject, isString, own } from "./json";
import { realDay, realMoment } from "./moment";

/** How a property is entered, from its type and its hint (the RFC's catalogue). */
type Control =
  | "text"
  | "textarea"
  | "date"
  | "date-time"
  | "email"
  | "uri"
  | "number"
  | "segments"
  | "select"
  | "checkboxes"
  | "switch"
  | "checkbox";

/** One of a field's choices: the value it gives, and its words. */
interface Choice {
  readonly value: string;
  readonly label: string;
}

/** A property as a field: its name, its words, its control, and what it allows. */
export interface Field {
  readonly name: string;
  readonly label: string;
  readonly description: string | null;
  readonly help: string | null;
  readonly placeholder: string | null;
  readonly required: boolean;
  readonly control: Control;
  readonly property: Property;
  readonly choices: readonly Choice[];
}

/** Fields under a title, or under none, keyed by their place. */
interface Group {
  readonly key: string;
  readonly title: string | null;
  readonly fields: readonly Field[];
}

/** A form as it is shown: its fields in groups, in order, and the words on its button. */
export interface Layout {
  readonly description: string | null;
  readonly groups: readonly Group[];
  readonly fields: readonly Field[];
  readonly submitLabel: string;
}

/** The most choices shown side by side: more, or an optional set without a default, is a select. */
const MOST_SEGMENTS = 5;

/** What a person has entered, by field, before it is read as values. */
export type Draft = Readonly<Record<string, string | boolean | readonly string[]>>;

const strings = (value: unknown): value is readonly string[] =>
  Array.isArray(value) && value.every(isString);

/** The most properties a form has, and choices a property. */
const MOST_PROPERTIES = 50;
const MOST_CHOICES = 64;

/** The longest a text may be, whatever its `maxLength` says. */
const LONGEST = 10_000;

/** The most a form's values weigh, in the UTF-8 bytes of their compact JSON. */
const MOST_VALUES_BYTES = 65_536;

/** A property's name: a letter or _, then up to 63 letters, digits, _ or -. */
const NAME = /^[A-Za-z_][A-Za-z0-9_-]{0,63}$/u;

/** Names that fit the pattern but that JavaScript objects treat apart. */
const RESERVED = new Set(["__proto__", "constructor", "prototype"]);

/** The keywords each kind of property may have, beside a title and a description. */
const KEYWORDS = {
  string: ["minLength", "maxLength", "format", "default"],
  choice: ["enum", "oneOf", "default"],
  number: ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "default"],
  boolean: ["default"],
  array: ["items", "uniqueItems", "minItems", "maxItems", "default"],
  items: ["enum", "oneOf"],
} as const;

/** The keywords a form's root may have, beside its type, title and description. */
const ROOT = ["properties", "required", "additionalProperties"];

const FORMATS = new Set(["date", "date-time", "email", "uri"]);

const WIDGETS = new Set(["textarea", "select", "checkbox"]);

/** Whether an object has these keywords alone, with its type, and a title and description that are words. */
const only = (value: Readonly<Record<string, unknown>>, keywords: readonly string[]) =>
  Object.keys(value).every(
    (key) => key === "type" || key === "title" || key === "description" || keywords.includes(key),
  ) &&
  (value.title === undefined || isString(value.title)) &&
  (value.description === undefined || isString(value.description));

/** A count a property may give: a whole number, none below 0. */
const isCount = (value: unknown): value is number =>
  isNumber(value) && Number.isInteger(value) && value >= 0;

/** Whether each of these keywords, where it is given, is as `is` says. */
const given = (
  property: Readonly<Record<string, unknown>>,
  keys: readonly string[],
  is: (value: unknown) => boolean,
) => keys.every((key) => property[key] === undefined || is(property[key]));

/** Whether no more than `most` is asked for at least, where both are given. */
const fits = (least: unknown, most: unknown) =>
  !(isNumber(least) && isNumber(most) && least > most);

/** A labelled choice: its value and its title, and nothing else. */
const isLabelled = (value: unknown): value is { readonly const: string; readonly title: string } =>
  isObject(value) &&
  Object.keys(value).every((key) => key === "const" || key === "title") &&
  isString(value.const) &&
  isString(value.title);

/**
 * A property's choices, as the values they give, or null where they aren't a set of choices: an
 * `enum` of strings or a `oneOf` of labelled choices, one of the two, 64 at most, each once.
 */
function choiceValues(source: Readonly<Record<string, unknown>>): readonly string[] | null {
  const { enum: listed, oneOf } = source;
  let values: readonly string[] | null = null;
  if (oneOf === undefined && strings(listed)) {
    values = listed;
  } else if (listed === undefined && Array.isArray(oneOf) && oneOf.every(isLabelled)) {
    values = oneOf.map((one) => one.const);
  }
  return values !== null &&
    values.length > 0 &&
    values.length <= MOST_CHOICES &&
    new Set(values).size === values.length
    ? values
    : null;
}

/**
 * Whether some number meets a number property's bounds, as the package checks them: each low
 * bound below each high one, or at it where both are closed.
 */
function reachable(property: Readonly<Record<string, unknown>>): boolean {
  const lows = [
    [property.minimum, false],
    [property.exclusiveMinimum, true],
  ] as const;
  const highs = [
    [property.maximum, false],
    [property.exclusiveMaximum, true],
  ] as const;
  return lows.every(([low, openLow]) =>
    highs.every(
      ([high, openHigh]) =>
        !(isNumber(low) && isNumber(high)) || low < high || (low === high && !openLow && !openHigh),
    ),
  );
}

/** A field of one property, alone, to check the property's default against. */
const alone = (property: Property): Field => ({
  name: "default",
  label: "default",
  description: null,
  help: null,
  placeholder: null,
  required: false,
  control: "text",
  property,
  choices: choicesOf(property),
});

/** A property of the subset's kinds, its keywords as the package allows them, or null. */
function kindOf(property: Readonly<Record<string, unknown>>): Property | null {
  const choices = property.enum !== undefined || property.oneOf !== undefined;
  const type = property.type ?? (choices ? "string" : undefined);
  if (type === "string" && choices) {
    return choiceValues(property) !== null && only(property, KEYWORDS.choice)
      ? ({ ...property, type } as Property)
      : null;
  }
  switch (type) {
    case "string":
      return only(property, KEYWORDS.string) &&
        given(property, ["minLength", "maxLength"], isCount) &&
        fits(property.minLength, property.maxLength) &&
        given(property, ["maxLength"], (most) => (most as number) <= LONGEST) &&
        given(property, ["format"], (format) => FORMATS.has(format as string))
        ? (property as Property)
        : null;
    case "number":
    case "integer": {
      const bounds = ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"];
      return only(property, KEYWORDS.number) &&
        given(property, bounds, isNumber) &&
        given(property, ["multipleOf"], (of) => (of as number) > 0) &&
        reachable(property)
        ? (property as Property)
        : null;
    }
    case "boolean":
      return only(property, KEYWORDS.boolean) ? (property as Property) : null;
    case "array": {
      const items = property.items;
      const values =
        isObject(items) &&
        (items.type === undefined || items.type === "string") &&
        only(items, KEYWORDS.items)
          ? choiceValues(items)
          : null;
      return values !== null &&
        only(property, KEYWORDS.array) &&
        given(property, ["minItems", "maxItems"], isCount) &&
        given(property, ["uniqueItems"], (unique) => typeof unique === "boolean") &&
        fits(property.minItems, property.maxItems) &&
        !(property.uniqueItems === true && !fits(property.minItems, values.length))
        ? (property as Property)
        : null;
    }
    default:
      return null;
  }
}

/**
 * A property as a form shows it, or null where the package's subset refuses it: an allow-list of
 * keywords for its kind, with a title and a description that are words; lengths and counts that
 * are whole and not below 0; bounds within JavaScript's safe integers that some value meets;
 * choices given once, as an enum or labelled; and a default the property itself takes. Choices
 * may leave out their `type`, as the package allows; they are strings. What the wire sends as
 * null is left out.
 */
function readProperty(written: unknown): Property | null {
  if (!isObject(written)) {
    return null;
  }
  const property = kindOf(
    Object.fromEntries(Object.entries(written).filter(([, value]) => value !== null)),
  );
  if (property === null || property.default === undefined) {
    return property;
  }
  return valueProblem(alone(property), property.default) === null ? property : null;
}

/**
 * A schema as a form can show it, or null where the package's subset refuses it: an object, its
 * `type` written or not, of 50 properties at most, each named as the subset names them and of its
 * kinds, every name it requires one of them, and no `additionalProperties` but false. A property
 * this can't show makes the whole form one it can't, rather than a form sent without it.
 */
export function readSchema(value: unknown): FormSchema | null {
  if (
    !isObject(value) ||
    (value.type ?? "object") !== "object" ||
    !only(value, ROOT) ||
    (value.additionalProperties ?? false) !== false
  ) {
    return null;
  }
  const { properties = {}, required = [] } = value;
  if (!(isObject(properties) && strings(required))) {
    return null;
  }
  const names = Object.keys(properties);
  const read = Object.entries(properties).map(([name, property]) => [name, readProperty(property)]);
  if (
    names.length > MOST_PROPERTIES ||
    names.some((name) => !NAME.test(name) || RESERVED.has(name)) ||
    read.some(([, property]) => property === null) ||
    required.some((name) => !names.includes(name)) ||
    new Set(required).size !== required.length
  ) {
    return null;
  }
  return {
    ...(value as FormSchema),
    type: "object",
    properties: Object.fromEntries(read),
    required: [...required],
  };
}

/** A property's hints, if each is what it may be. */
const isFieldHints = (value: unknown) =>
  isObject(value) &&
  Object.keys(value).every((key) => key === "widget" || key === "placeholder" || key === "help") &&
  (value.widget == null || WIDGETS.has(value.widget as string)) &&
  (value.placeholder == null || isString(value.placeholder)) &&
  (value.help == null || isString(value.help));

/** A section: a title, and the names of its properties. */
const isSection = (value: unknown) =>
  isObject(value) && isString(value.title) && strings(value.properties);

/**
 * Hints, where they are what hints may be: hints by property, an order of names, sections and the
 * button's words. Hints that aren't are none, so the form shows as its schema has it.
 */
function readHints(value: unknown): UiHints | null {
  if (!isObject(value)) {
    return null;
  }
  const { fields, order, sections, submit_label } = value;
  const read =
    (fields == null || (isObject(fields) && Object.values(fields).every(isFieldHints))) &&
    (order == null || strings(order)) &&
    (sections == null || (Array.isArray(sections) && sections.every(isSection))) &&
    (submit_label == null || isString(submit_label));
  return read ? (value as UiHints) : null;
}

/** An `ask_form` request's arguments, as a form to show, or null where they aren't one. */
export function readAskForm(args: unknown): AskForm | null {
  const schema = isObject(args) ? readSchema(args.schema) : null;
  if (!(isObject(args) && schema)) {
    return null;
  }
  return { title: isString(args.title) ? args.title : "", schema, ui: readHints(args.ui) };
}

/** A `form` artifact's data, as a form to show, or null where it isn't one. */
export function readForm(data: unknown): Form | null {
  const schema = isObject(data) ? readSchema(data.schema) : null;
  if (!(isObject(data) && schema)) {
    return null;
  }
  const submissions = data.submissions;
  return {
    title: isString(data.title) ? data.title : "",
    schema,
    ui: readHints(data.ui),
    submissions: submissions === "per_person" || submissions === "many" ? submissions : "once",
    closed: data.closed === true,
  };
}

/** A property's choices, as values and words, or none. */
function choicesOf(property: Property): readonly Choice[] {
  const source = property.type === "array" ? property.items : property;
  if ("oneOf" in source && source.oneOf) {
    return source.oneOf.map((one) => ({ value: one.const, label: one.title }));
  }
  if ("enum" in source && source.enum) {
    return source.enum.map((value) => ({ value, label: value }));
  }
  return [];
}

/** The control a property is entered with: its type's default, unless its hint names another. */
function controlOf(
  property: Property,
  choices: readonly Choice[],
  required: boolean,
  hints: PropertyHints,
): Control {
  switch (property.type) {
    case "boolean":
      return hints.widget === "checkbox" ? "checkbox" : "switch";
    case "number":
    case "integer":
      return "number";
    case "array":
      return "checkboxes";
    default:
      break;
  }
  if (choices.length > 0) {
    const few = choices.length <= MOST_SEGMENTS && (required || property.default !== undefined);
    return few && hints.widget !== "select" ? "segments" : "select";
  }
  if (property.format) {
    return property.format;
  }
  return hints.widget === "textarea" ? "textarea" : "text";
}

/**
 * A schema and its hints, as fields in groups: each section's fields under its title, in the
 * order it names them, then the rest, in the hints' `order` and then the schema's own. A hint
 * that names no property is passed over.
 */
export function layoutOf(schema: FormSchema, ui: UiHints | null | undefined, title = ""): Layout {
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const hinted = ui?.fields ?? {};
  const named = Object.keys(properties);
  const order = [
    ...new Set([...(ui?.order ?? []).filter((name) => Object.hasOwn(properties, name)), ...named]),
  ];
  const fields = new Map(
    order.map((name) => {
      const property = properties[name] as Property;
      const hints = (own(hinted, name) ?? {}) as PropertyHints;
      const choices = choicesOf(property);
      const field: Field = {
        name,
        label: property.title ?? name,
        description: property.description ?? null,
        help: hints.help ?? null,
        placeholder: hints.placeholder ?? null,
        required: required.has(name),
        control: controlOf(property, choices, required.has(name), hints),
        property,
        choices,
      };
      return [name, field];
    }),
  );
  const placed = new Set<string>();
  const groups: Group[] = [];
  for (const section of ui?.sections ?? []) {
    const inIt = section.properties.flatMap((name) => {
      const field = fields.get(name);
      if (!field || placed.has(name)) {
        return [];
      }
      placed.add(name);
      return [field];
    });
    if (inIt.length > 0) {
      groups.push({ key: `section-${groups.length}`, title: section.title, fields: inIt });
    }
  }
  const rest = [...fields.values()].filter((field) => !placed.has(field.name));
  if (rest.length > 0) {
    groups.unshift({ key: "untitled", title: null, fields: rest });
  }
  return {
    description: schema.description ?? null,
    groups,
    fields: groups.flatMap((group) => group.fields),
    submitLabel: ui?.submit_label || title || "Send",
  };
}

/** A field's entry before a person changes it: its default, or nothing. */
function startOf(field: Field): string | boolean | readonly string[] {
  const { property } = field;
  switch (property.type) {
    case "boolean":
      return property.default ?? false;
    case "array":
      return property.default ?? [];
    case "number":
    case "integer":
      return property.default === undefined ? "" : String(property.default);
    default:
      return property.format === "date-time" && property.default !== undefined
        ? localOf(property.default)
        : (property.default ?? "");
  }
}

/** Every field's entry before a person changes it. */
export const draftOf = (fields: readonly Field[]): Draft =>
  Object.fromEntries(fields.map((field) => [field.name, startOf(field)]));

/** A number as a refusal says it: grouped, as British English writes it. */
const said = (value: number) => value.toLocaleString("en-GB");

/** A string's length as JSON Schema counts it: in code points, not UTF-16 units. */
const lengthOf = (text: string) => [...text].length;

/** A domain's label: letters, digits and inner hyphens, 63 at most. */
const LABEL = "[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?";

/** An address: a name, an @, and a domain of two labels or more, as the package's check has it. */
const EMAIL = new RegExp(`^[^\\s@]{1,64}@${LABEL}(?:\\.${LABEL})+$`, "u");

/** The longest an address is, in characters, as the package's check has it. */
const LONGEST_EMAIL = 254;

/** A web or mail address, and no white space, as the package's check has it. */
const URI = /^(https?:\/\/|mailto:)\S+$/iu;

/** A moment as the browser's date and time input gives it: to the minute, or to the second. */
const LOCAL = /^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/u;

/** A number as a person writes it in a form: decimal, with a point and an exponent if they like. */
const DECIMAL = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/u;

/**
 * A moment as the browser's date and time input gives it, in the reader's zone, as RFC 3339 in
 * UTC; or null where it names no moment.
 */
export function momentOf(local: string): string | null {
  if (!(LOCAL.test(local) && realDay(local.slice(0, 10)))) {
    return null;
  }
  return new Date(local).toISOString();
}

/** A moment as the date and time input shows it: in the reader's zone, its seconds kept. */
function localOf(moment: string): string {
  if (!realMoment(moment)) {
    return "";
  }
  const at = new Date(moment.toUpperCase());
  const two = (part: number) => String(part).padStart(2, "0");
  const year = String(at.getFullYear()).padStart(4, "0");
  const seconds = at.getSeconds() === 0 ? "" : `:${two(at.getSeconds())}`;
  return `${year}-${two(at.getMonth() + 1)}-${two(at.getDate())}T${two(at.getHours())}:${two(at.getMinutes())}${seconds}`;
}

/** What a format's refusal says. */
const FORMAT_SAID = {
  email: "Enter an email address, such as name@example.com.",
  uri: "Enter a whole address, such as https://example.com.",
  date: "Enter a date.",
  "date-time": "Enter a date and a time.",
} as const;

/** Whether a text is in its format, as the package checks each. */
const FORMATTED = {
  email: (text: string) => text.length <= LONGEST_EMAIL && EMAIL.test(text),
  uri: (text: string) => URI.test(text),
  date: realDay,
  "date-time": realMoment,
} as const;

/** Why a text entry isn't one its property allows, or null. */
function textProblem(field: Field, text: string): string | null {
  const property = field.property;
  if (property.type !== "string") {
    return null;
  }
  if (field.choices.length > 0) {
    return field.choices.some((choice) => choice.value === text) ? null : "Choose one of these.";
  }
  const length = lengthOf(text);
  const longest = Math.min(property.maxLength ?? LONGEST, LONGEST);
  if (property.minLength !== undefined && length < property.minLength) {
    return `Use ${said(property.minLength)} characters or more.`;
  }
  if (length > longest) {
    return `Use ${said(longest)} characters or fewer.`;
  }
  const { format } = property;
  return format === undefined || FORMATTED[format](text) ? null : FORMAT_SAID[format];
}

/**
 * What a field allows, said before anything is entered, so its refusal is never the first a person
 * hears of it: a number's range, a text's longest, how many choices to make. Null where it allows
 * anything its control takes.
 */
export function limitsOf(field: Field): string | null {
  const property = field.property;
  switch (property.type) {
    case "number":
    case "integer": {
      const low = property.minimum;
      const high = property.maximum;
      if (low !== undefined && high !== undefined) {
        return `From ${said(low)} to ${said(high)}.`;
      }
      if (low !== undefined) {
        return `${said(low)} or more.`;
      }
      return high === undefined ? null : `Up to ${said(high)}.`;
    }
    case "array": {
      const fewest = property.minItems;
      const most = property.maxItems;
      if (fewest !== undefined && most !== undefined) {
        return fewest === most
          ? `Choose ${said(most)}.`
          : `Choose ${said(fewest)} to ${said(most)}.`;
      }
      if (fewest !== undefined) {
        return `Choose ${said(fewest)} or more.`;
      }
      return most === undefined ? null : `Choose up to ${said(most)}.`;
    }
    case "string":
      return property.maxLength === undefined || field.choices.length > 0
        ? null
        : `Up to ${said(property.maxLength)} characters.`;
    default:
      return null;
  }
}

/**
 * Whether a number is a whole multiple of another, to within a billionth of their quotient, as the
 * package checks it.
 */
const multiple = (value: number, of: number) => {
  const times = value / of;
  if (!Number.isFinite(times)) {
    return false; // a quotient too large for a number is no multiple, as the package has it
  }
  const whole = Math.round(times);
  return whole * of === value || Math.abs(times - whole) <= 1e-9 * Math.abs(times);
};

/** Why a number isn't one its property allows, or null. */
function numberProblem(field: Field, value: number): string | null {
  const property = field.property;
  if (property.type !== "number" && property.type !== "integer") {
    return null;
  }
  if (!Number.isFinite(value)) {
    return "Enter a number.";
  }
  if (!isNumber(value)) {
    return "Enter a smaller number.";
  }
  if (property.type === "integer" && !Number.isInteger(value)) {
    return "Enter a whole number.";
  }
  if (property.minimum !== undefined && value < property.minimum) {
    return `Enter ${said(property.minimum)} or more.`;
  }
  if (property.exclusiveMinimum !== undefined && value <= property.exclusiveMinimum) {
    return `Enter more than ${said(property.exclusiveMinimum)}.`;
  }
  if (property.maximum !== undefined && value > property.maximum) {
    return `Enter ${said(property.maximum)} or less.`;
  }
  if (property.exclusiveMaximum !== undefined && value >= property.exclusiveMaximum) {
    return `Enter less than ${said(property.exclusiveMaximum)}.`;
  }
  if (property.multipleOf !== undefined && !multiple(value, property.multipleOf)) {
    return `Enter a multiple of ${said(property.multipleOf)}.`;
  }
  return null;
}

/** Why a set of choices isn't one its property allows, or null. */
function choicesProblem(field: Field, chosen: readonly string[]): string | null {
  const property = field.property;
  if (property.type !== "array") {
    return null;
  }
  if (property.minItems !== undefined && chosen.length < property.minItems) {
    return `Choose ${said(property.minItems)} or more.`;
  }
  if (property.maxItems !== undefined && chosen.length > property.maxItems) {
    return `Choose ${said(property.maxItems)} or fewer.`;
  }
  if (chosen.some((value) => !field.choices.some((choice) => choice.value === value))) {
    return "Choose among these.";
  }
  return property.uniqueItems === true && new Set(chosen).size !== chosen.length
    ? "Choose each once."
    : null;
}

/** What a field left empty is told, by its control. */
const EMPTY: Record<Control, string> = {
  text: "Enter an answer.",
  textarea: "Enter an answer.",
  date: "Enter a date.",
  "date-time": "Enter a date and a time.",
  email: "Enter an email address.",
  uri: "Enter an address.",
  number: "Enter a number.",
  segments: "Choose one.",
  select: "Choose one.",
  checkboxes: "Choose at least one.",
  switch: "Choose yes or no.",
  checkbox: "Choose yes or no.",
};

/** Why a value isn't one its field allows, by its type first, then by what the field allows. */
function valueProblem(field: Field, value: unknown): string | null {
  switch (field.property.type) {
    case "string":
      return typeof value === "string" ? textProblem(field, value) : EMPTY[field.control];
    case "number":
    case "integer":
      return typeof value === "number" ? numberProblem(field, value) : "Enter a number.";
    case "boolean":
      return typeof value === "boolean" ? null : "Choose yes or no.";
    default:
      return strings(value) ? choicesProblem(field, value) : "Choose among these.";
  }
}

/**
 * Why each of some values isn't what the form allows, by field, as the package's check refuses
 * them: a field it asks for that is missing, one it doesn't have, or a value its property
 * refuses. What isn't values at all is refused as a whole, under "".
 */
export function problemsOf(
  fields: readonly Field[],
  values: unknown,
): Readonly<Record<string, string>> {
  if (!isObject(values)) {
    return { "": "Send the answers as a set of fields." };
  }
  const problems: Record<string, string> = {};
  const named = new Set(fields.map((field) => field.name));
  for (const name of Object.keys(values).filter((key) => !named.has(key))) {
    problems[name] = "This form has no such field.";
  }
  for (const field of fields) {
    const value = own(values, field.name);
    const problem =
      value === undefined
        ? field.required
          ? EMPTY[field.control]
          : null
        : valueProblem(field, value);
    if (problem !== null) {
      problems[field.name] = problem;
    }
  }
  return problems;
}

/**
 * One field's entry as its value, or why it can't be one. An entry of white space alone is none,
 * so a required text of nothing but spaces is refused here, as empty; a line is trimmed, and a
 * text area's text sent as it was written. A set of choices left empty is none where the field is
 * optional, and the empty set where it is required, which the package takes unless it asks for
 * more. A number is read as decimal alone, and a date and time is sent in UTC.
 */
function read(field: Field, entry: string | boolean | readonly string[]) {
  if (typeof entry === "boolean") {
    return { value: entry, problem: null };
  }
  if (typeof entry !== "string") {
    return { value: entry.length > 0 || field.required ? [...entry] : undefined, problem: null };
  }
  const text = entry.trim();
  if (text === "") {
    return { value: undefined, problem: null };
  }
  if (field.control === "number") {
    return DECIMAL.test(text)
      ? { value: Number(text), problem: null }
      : { value: undefined, problem: "Enter a number." };
  }
  if (field.control === "date-time") {
    const moment = momentOf(text);
    return moment === null
      ? { value: undefined, problem: "Enter a date and a time." }
      : { value: moment, problem: null };
  }
  return { value: field.control === "textarea" ? entry : text, problem: null };
}

/** How much values weigh, as the package measures them: the UTF-8 bytes of their compact JSON. */
const bytesOf = (values: Values) => new TextEncoder().encode(JSON.stringify(values)).length;

/**
 * What a person entered, as values; why each refused field is refused, checked as the package
 * checks them; and what is wrong with the answers as a whole. A field left empty is left out of
 * the values, so an optional one is never sent as `""`; a switch is always sent, as what it
 * shows.
 */
export function valuesOf(
  fields: readonly Field[],
  draft: Draft,
): {
  readonly values: Values;
  readonly problems: Readonly<Record<string, string>>;
  readonly whole: string | null;
} {
  const values: Record<string, Value> = {};
  const unread: Record<string, string> = {};
  for (const field of fields) {
    const entry = (own(draft, field.name) as Draft[string] | undefined) ?? startOf(field);
    const { value, problem } = read(field, entry);
    if (problem !== null) {
      unread[field.name] = problem;
    } else if (value !== undefined) {
      values[field.name] = value;
    }
  }
  const checked = problemsOf(
    fields.filter((field) => unread[field.name] === undefined),
    values,
  );
  const whole =
    bytesOf(values) > MOST_VALUES_BYTES
      ? "These answers are too long to send: shorten the longest."
      : null;
  return { values, problems: { ...checked, ...unread }, whole };
}

/** What a field's value the server refused says, where the kit has no words of its own. */
const NOT_VALID = "This isn't valid.";

/**
 * A server's error under a field, in the kit's words, by the error's type: a field left out, a
 * format, or a choice not offered, as this side says them too; anything else isn't valid. Never
 * the server's own message (portalr ADR-0070).
 */
function saidOf(field: Field | undefined, type: unknown): string {
  const property = field?.property;
  switch (type) {
    case "missing":
      return field ? EMPTY[field.control] : NOT_VALID;
    case "format":
      return property?.type === "string" && property.format !== undefined
        ? FORMAT_SAID[property.format]
        : NOT_VALID;
    case "enum":
      return field?.control === "checkboxes" ? "Choose among these." : "Choose one of these.";
    default:
      return NOT_VALID;
  }
}

/**
 * A server's refusal of a form's values, put under the fields it names: a `validation_failed`
 * rejection's errors, each by the first part of its `loc` that names a field, as Pydantic's
 * errors carry it; what names none is the form's own. Null for any other rejection.
 */
export function refusalsOf(
  rejection: unknown,
  fields: readonly Field[],
): { readonly fields: Readonly<Record<string, string>>; readonly form: readonly string[] } | null {
  if (!(isObject(rejection) && rejection.type === "validation_failed")) {
    return null;
  }
  const byName = new Map(fields.map((field) => [field.name, field]));
  const byField: Record<string, string> = {};
  const form: string[] = [];
  const unnamed: unknown[] = [];
  const errors = Array.isArray(rejection.errors) ? rejection.errors : [];
  for (const error of errors) {
    if (!isObject(error)) {
      continue;
    }
    const loc = Array.isArray(error.loc) ? error.loc : [];
    const name = loc.find((part): part is string => isString(part) && byName.has(part));
    if (name === undefined) {
      unnamed.push(error);
    } else {
      byField[name] ??= saidOf(byName.get(name), error.type);
    }
  }
  // What names no field is the form's own: the kit's sentence, with where, by the paths alone.
  if (unnamed.length > 0 || errors.length === 0) {
    const paths = pathsOf(unnamed);
    form.push(paths.length > 0 ? `${INVALID.slice(0, -1)}: ${paths.join(", ")}.` : INVALID);
  }
  return { fields: byField, form };
}

/**
 * Why a form's submission or answer can't be made: the form changed or is closed (artifactr.ui's
 * reasons), it was answered already (an invalid state with no reason), or an integration it needs
 * is off in the workspace (artifactr's `not_enabled`, which names it).
 */
export type Ended =
  | { readonly reason: RefusalReason | "answered" }
  | { readonly reason: "off"; readonly integration: string };

/**
 * Why a form's submission or answer was refused, from the rejection's type and `reason`, never its
 * message. Null for any other rejection, or a reason this doesn't know.
 */
export function endedBy(rejection: unknown): Ended | null {
  if (!isObject(rejection)) {
    return null;
  }
  if (rejection.type === "not_enabled") {
    return isString(rejection.integration)
      ? { reason: "off", integration: rejection.integration }
      : null;
  }
  if (rejection.type !== "invalid_state") {
    return null;
  }
  switch (rejection.reason) {
    // No reason is artifactr's own `invalid_state` (`core/rules.py`): an artifact whose id already
    // exists, which for a submission, whose id is derived, is this one made already; or a deferred
    // request already answered.
    case undefined:
      return { reason: "answered" };
    case "changed":
    case "closed":
      return { reason: rejection.reason };
    default:
      return null;
  }
}
