import { describe, expect, test } from "vitest";
import FORMS_JSON from "../../../../artifactr/tests/ui/vectors/forms.json?raw";
import type { FormSchema, Property } from "./artifactr-ui";
import {
  draftOf,
  endedBy,
  type Field,
  layoutOf,
  limitsOf,
  momentOf,
  problemsOf,
  readAskForm,
  readForm,
  readSchema,
  refusalsOf,
  valuesOf,
} from "./form-schema";

const schema = (properties: Record<string, Property>, required: string[] = []): FormSchema => ({
  type: "object",
  properties,
  required,
});

/** The one field of a schema of one property. */
const fieldOf = (
  property: Property,
  required = false,
  widget?: "textarea" | "select" | "checkbox",
) =>
  layoutOf(
    schema({ it: property }, required ? ["it"] : []),
    widget ? { fields: { it: { widget } } } : null,
  ).fields[0] as Field;

/** Why one field's entry is refused, or null. */
const problem = (field: Field, entry: string | boolean | readonly string[]) =>
  valuesOf([field], { [field.name]: entry }).problems[field.name] ?? null;

/** A schema of no properties, as it is read. */
const NONE = { type: "object", properties: {}, required: [] };

describe("reading a schema", () => {
  test("an object of the subset's types is read as it is", () => {
    const read = schema({
      name: { type: "string" },
      size: { type: "string", enum: ["S", "M"] },
      tone: {
        type: "string",
        oneOf: [
          { const: "a", title: "A" },
          { const: "b", title: "B" },
        ],
      },
      count: { type: "integer" },
      rate: { type: "number" },
      ok: { type: "boolean" },
      tags: { type: "array", items: { enum: ["x"] } },
      kinds: { type: "array", items: { oneOf: [{ const: "k", title: "K" }] } },
    });
    expect(readSchema(read)).toEqual(read);
  });

  test("an object with no properties is a form of none, its type written or not", () => {
    const none = { type: "object", properties: {}, required: [] };
    expect(readSchema({ type: "object" })).toEqual(none);
    expect(readSchema({})).toEqual(none);
  });

  test("choices without a type are strings, as the package reads them", () => {
    expect(readSchema({ properties: { size: { enum: ["S"] } } })?.properties).toEqual({
      size: { type: "string", enum: ["S"] },
    });
  });

  test.each([
    ["not an object", "form"],
    ["an array", []],
    ["another type", { type: "string" }],
    ["properties that aren't an object", { type: "object", properties: [] }],
    ["a property that isn't an object", { type: "object", properties: { a: "string" } }],
    ["a type outside the subset", { type: "object", properties: { a: { type: "object" } } }],
    [
      "choices that aren't strings",
      { type: "object", properties: { a: { type: "string", enum: [1] } } },
    ],
    [
      "labelled choices without a value",
      { type: "object", properties: { a: { type: "string", oneOf: [{ title: "A" }] } } },
    ],
    [
      "labelled choices without a title",
      { type: "object", properties: { a: { type: "string", oneOf: [{ const: "a" }] } } },
    ],
    [
      "labelled choices with a title that isn't text",
      { type: "object", properties: { a: { type: "string", oneOf: [{ const: "a", title: 1 }] } } },
    ],
    ["an array of anything", { type: "object", properties: { a: { type: "array", items: {} } } }],
    ["an array without items", { type: "object", properties: { a: { type: "array" } } }],
    ["required that isn't names", { type: "object", required: [1] }],
  ])("%s is no form", (_, value) => {
    expect(readSchema(value)).toBeNull();
  });

  test("an ask_form request's arguments are its title, schema and hints", () => {
    const asked = readAskForm({ title: "Leave", schema: { type: "object" }, ui: { order: [] } });
    expect(asked).toEqual({ title: "Leave", schema: NONE, ui: { order: [] } });
  });

  test("an ask_form request without a title or hints has none", () => {
    expect(readAskForm({ schema: { type: "object" }, ui: "bold" })).toEqual({
      title: "",
      schema: NONE,
      ui: null,
    });
  });

  test.each([null, { title: "x" }, { schema: { type: "array" } }])(
    "arguments without a form, %j, are none",
    (args) => {
      expect(readAskForm(args)).toBeNull();
    },
  );

  test("a form artifact's data are read, with its submissions and whether it is closed", () => {
    const data = {
      title: "Poll",
      schema: { type: "object" },
      submissions: "per_person",
      closed: true,
    };
    expect(readForm(data)).toEqual({ ...data, schema: NONE, ui: null });
    expect(readForm({ ...data, submissions: "many" })?.submissions).toBe("many");
  });

  test("a form artifact without its settings is answered once, open, untitled", () => {
    expect(readForm({ schema: { type: "object" }, submissions: "always" })).toEqual({
      title: "",
      schema: NONE,
      ui: null,
      submissions: "once",
      closed: false,
    });
  });

  test.each([null, { title: "x" }])("data without a schema, %j, are no form", (data) => {
    expect(readForm(data)).toBeNull();
  });
});

describe("laying a form out", () => {
  test.each([
    ["one line", { type: "string" }, false, undefined, "text"],
    ["a text area", { type: "string" }, false, "textarea", "textarea"],
    ["a date", { type: "string", format: "date" }, false, undefined, "date"],
    ["a date and time", { type: "string", format: "date-time" }, false, undefined, "date-time"],
    ["an email", { type: "string", format: "email" }, false, undefined, "email"],
    ["an address", { type: "string", format: "uri" }, false, undefined, "uri"],
    ["a number", { type: "number" }, false, undefined, "number"],
    ["a whole number", { type: "integer" }, false, undefined, "number"],
    ["a switch", { type: "boolean" }, false, undefined, "switch"],
    ["a checkbox", { type: "boolean" }, false, "checkbox", "checkbox"],
    ["checkboxes", { type: "array", items: { enum: ["a"] } }, false, undefined, "checkboxes"],
    ["segments, required", { type: "string", enum: ["a", "b"] }, true, undefined, "segments"],
    [
      "segments, with a default",
      { type: "string", enum: ["a", "b"], default: "a" },
      false,
      undefined,
      "segments",
    ],
    ["a select, optional", { type: "string", enum: ["a", "b"] }, false, undefined, "select"],
    ["a select, asked for", { type: "string", enum: ["a", "b"] }, true, "select", "select"],
    [
      "a select, of six",
      { type: "string", enum: ["a", "b", "c", "d", "e", "f"] },
      true,
      undefined,
      "select",
    ],
  ] as const)("%s", (_, property, required, widget, control) => {
    expect(fieldOf(property as Property, required, widget).control).toBe(control);
  });

  test("a field takes its words from its property and its hints", () => {
    const layout = layoutOf(
      schema({ email: { type: "string", title: "Email", description: "Where we write." } }, [
        "email",
      ]),
      { fields: { email: { help: "Work, not home.", placeholder: "name@example.com" } } },
    );
    expect(layout.fields[0]).toMatchObject({
      name: "email",
      label: "Email",
      description: "Where we write.",
      help: "Work, not home.",
      placeholder: "name@example.com",
      required: true,
    });
  });

  test("a field without a title is named by its property", () => {
    expect(fieldOf({ type: "string" })).toMatchObject({
      label: "it",
      description: null,
      help: null,
    });
  });

  test("labelled choices show their titles; an enum's, their values", () => {
    expect(
      fieldOf({
        type: "string",
        oneOf: [
          { const: "a", title: "Ay" },
          { const: "b", title: "Bee" },
        ],
      }).choices,
    ).toEqual([
      { value: "a", label: "Ay" },
      { value: "b", label: "Bee" },
    ]);
    expect(fieldOf({ type: "string", enum: ["a"] }).choices).toEqual([{ value: "a", label: "a" }]);
    expect(
      fieldOf({ type: "array", items: { oneOf: [{ const: "x", title: "Ex" }] } }).choices,
    ).toEqual([{ value: "x", label: "Ex" }]);
  });

  test("the fields follow the hints' order, then the schema's, and sections group them", () => {
    const layout = layoutOf(
      schema({
        a: { type: "string" },
        b: { type: "string" },
        c: { type: "string" },
        d: { type: "string" },
      }),
      {
        order: ["c", "gone", "a"],
        sections: [
          { title: "Later", properties: ["d", "b", "missing"] },
          { title: "Again", properties: ["b"] },
        ],
      },
    );
    expect(layout.groups.map((group) => [group.title, group.fields.map((f) => f.name)])).toEqual([
      [null, ["c", "a"]],
      ["Later", ["d", "b"]],
    ]);
    expect(layout.fields.map((field) => field.name)).toEqual(["c", "a", "d", "b"]);
  });

  test("a form whose every field is in a section has no untitled group", () => {
    const layout = layoutOf(schema({ a: { type: "string" } }), {
      sections: [{ title: "All", properties: ["a"] }],
    });
    expect(layout.groups.map((group) => group.title)).toEqual(["All"]);
  });

  test("the button says the hint's words, else the form's title, else Send", () => {
    const empty = schema({});
    expect(layoutOf(empty, { submit_label: "Book it" }, "Leave").submitLabel).toBe("Book it");
    expect(layoutOf(empty, null, "Leave").submitLabel).toBe("Leave");
    expect(layoutOf(empty, null).submitLabel).toBe("Send");
    expect(layoutOf({ type: "object", description: "Why." }, null).description).toBe("Why.");
    expect(layoutOf({ type: "object" }, null).description).toBeNull();
  });
});

describe("what a person enters", () => {
  test("each field starts at its default, or empty", () => {
    const layout = layoutOf(
      schema({
        a: { type: "string", default: "x" },
        b: { type: "string" },
        c: { type: "integer", default: 3 },
        d: { type: "number" },
        e: { type: "boolean", default: true },
        f: { type: "boolean" },
        g: { type: "array", items: { enum: ["p", "q"] }, default: ["q"] },
        h: { type: "array", items: { enum: ["p"] } },
      }),
      null,
    );
    expect(draftOf(layout.fields)).toEqual({
      a: "x",
      b: "",
      c: "3",
      d: "",
      e: true,
      f: false,
      g: ["q"],
      h: [],
    });
  });

  test("a date and time's default is shown in the reader's zone, to the minute", () => {
    const field = fieldOf({ type: "string", format: "date-time", default: "2026-10-17T09:30:00Z" });
    const shown = draftOf([field]).it as string;
    expect(shown).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(momentOf(shown)).toBe("2026-10-17T09:30:00.000Z");
    const unreadable = fieldOf({ type: "string", format: "date-time", default: "soon" });
    expect(draftOf([unreadable]).it).toBe("");
  });

  test("values leave an empty field out, send a switch as it shows, and a number as a number", () => {
    const layout = layoutOf(
      schema({
        name: { type: "string" },
        note: { type: "string" },
        age: { type: "integer" },
        ok: { type: "boolean" },
        tags: { type: "array", items: { enum: ["a", "b"] } },
        none: { type: "array", items: { enum: ["a"] } },
        when: { type: "string", format: "date-time" },
      }),
      null,
    );
    const { values, problems } = valuesOf(layout.fields, {
      name: "  Alice  ",
      note: "   ",
      age: "42",
      ok: false,
      tags: ["b"],
      none: [],
      when: "2026-10-17T09:30",
    });
    expect(problems).toEqual({});
    expect(values).toEqual({
      name: "Alice",
      age: 42,
      ok: false,
      tags: ["b"],
      when: momentOf("2026-10-17T09:30"),
    });
  });

  test("a field missing from the draft is read from its start", () => {
    const field = fieldOf({ type: "string", default: "x" });
    expect(valuesOf([field], {}).values).toEqual({ it: "x" });
  });

  test.each([
    ["text", { type: "string" }, "Enter an answer."],
    ["a date", { type: "string", format: "date" }, "Enter a date."],
    ["a date and time", { type: "string", format: "date-time" }, "Enter a date and a time."],
    ["an email", { type: "string", format: "email" }, "Enter an email address."],
    ["an address", { type: "string", format: "uri" }, "Enter an address."],
    ["a number", { type: "number" }, "Enter a number."],
    ["segments", { type: "string", enum: ["a"] }, "Choose one."],
    [
      "checkboxes, of one at least",
      { type: "array", items: { enum: ["a"] }, minItems: 1 },
      "Choose 1 or more.",
    ],
  ] as const)("a required %s left empty is refused", (_, property, said) => {
    const field = fieldOf(property as Property, true);
    expect(problem(field, field.control === "checkboxes" ? [] : "")).toBe(said);
  });

  test("a required select, a text area, a switch and a checkbox say what they need", () => {
    expect(problem(fieldOf({ type: "string", enum: ["a"] }, true, "select"), "")).toBe(
      "Choose one.",
    );
    expect(problem(fieldOf({ type: "string" }, true, "textarea"), "")).toBe("Enter an answer.");
    // A switch is always a value: required, it is never empty.
    expect(problem(fieldOf({ type: "boolean" }, true), false)).toBeNull();
    expect(problem(fieldOf({ type: "boolean" }, true, "checkbox"), true)).toBeNull();
  });

  test("an optional field left empty is no refusal", () => {
    expect(problem(fieldOf({ type: "string", minLength: 3 }), "")).toBeNull();
    expect(problem(fieldOf({ type: "array", items: { enum: ["a"] }, minItems: 1 }), [])).toBeNull();
  });

  test.each([
    [{ type: "string", minLength: 3 }, "ab", "Use 3 characters or more."],
    [{ type: "string", minLength: 3 }, "abc", null],
    [{ type: "string", maxLength: 2 }, "abc", "Use 2 characters or fewer."],
    [{ type: "string", maxLength: 10_000 }, "x".repeat(10_001), "Use 10,000 characters or fewer."],
    // Counted in code points, as JSON Schema counts them: one emoji is one character.
    [{ type: "string", maxLength: 1 }, "😀", null],
    [
      { type: "string", format: "email" },
      "alice@",
      "Enter an email address, such as name@example.com.",
    ],
    [{ type: "string", format: "email" }, "alice@acme.test", null],
    [
      { type: "string", format: "uri" },
      "acme.test",
      "Enter a whole address, such as https://example.com.",
    ],
    [{ type: "string", format: "uri" }, "https://acme.test/x", null],
    [{ type: "string", format: "date" }, "2026-02-30", "Enter a date."],
    [{ type: "string", format: "date" }, "17/10/2026", "Enter a date."],
    [{ type: "string", format: "date" }, "2026-10-17", null],
    [{ type: "string", format: "date-time" }, "later", "Enter a date and a time."],
    [{ type: "string", format: "date-time" }, "2026-10-17T09:30", null],
    [{ type: "string", enum: ["a", "b"] }, "c", "Choose one of these."],
    [{ type: "string", enum: ["a", "b"] }, "b", null],
  ] as const)("text %j as %j: %s", (property, entry, said) => {
    expect(problem(fieldOf(property as Property), entry)).toBe(said);
  });

  test.each([
    [{ type: "number" }, "many", "Enter a number."],
    [{ type: "number" }, "Infinity", "Enter a number."],
    [{ type: "integer" }, "1.5", "Enter a whole number."],
    [{ type: "number", minimum: 2 }, "1", "Enter 2 or more."],
    [{ type: "number", minimum: 2 }, "2", null],
    [{ type: "number", exclusiveMinimum: 2 }, "2", "Enter more than 2."],
    [{ type: "number", maximum: 1500 }, "1501", "Enter 1,500 or less."],
    [{ type: "number", maximum: 1500 }, "1500", null],
    [{ type: "number", exclusiveMaximum: 2 }, "2", "Enter less than 2."],
    [{ type: "number", multipleOf: 0.5 }, "1.25", "Enter a multiple of 0.5."],
    // 0.3 is not a binary fraction: 0.3 / 0.1 is 2.9999999999999996, which is still a multiple.
    [{ type: "number", multipleOf: 0.1 }, "0.3", null],
  ] as const)("number %j as %j: %s", (property, entry, said) => {
    expect(problem(fieldOf(property as Property), entry)).toBe(said);
  });

  test.each([
    [{ minItems: 2 }, ["a"], "Choose 2 or more."],
    [{ maxItems: 1 }, ["a", "b"], "Choose 1 or fewer."],
    [{ minItems: 1, maxItems: 2 }, ["a", "b"], null],
  ] as const)("choices %j of %j: %s", (bounds, chosen, said) => {
    const field = fieldOf({ type: "array", items: { enum: ["a", "b"] }, ...bounds });
    expect(problem(field, chosen)).toBe(said);
  });
});

describe("a server's refusal", () => {
  const fields = layoutOf(
    schema({ email: { type: "string" }, age: { type: "integer" } }),
    null,
  ).fields;

  test("is put under the fields its errors name, by the first part of the place that names one", () => {
    const refused = refusalsOf(
      {
        type: "validation_failed",
        message: "values are invalid",
        errors: [
          { loc: ["answer", "email"], msg: "value is not a valid email address" },
          { loc: ["email"], msg: "a second error, not shown" },
          { loc: ["age"], msg: "Input should be a valid integer." },
          { loc: [], msg: "too many values" },
          { loc: ["email"] },
          "not an error",
        ],
      },
      fields,
    );
    // The kit's words under each field, never the server's; what names no field, the form's.
    expect(refused).toEqual({
      fields: { email: "This isn't valid.", age: "This isn't valid." },
      form: ["What was asked for isn't valid."],
    });
  });

  test("without errors, the form isn't valid, whatever its message says", () => {
    const invalid = { fields: {}, form: ["What was asked for isn't valid."] };
    expect(refusalsOf({ type: "validation_failed", message: "no" }, fields)).toEqual(invalid);
    expect(refusalsOf({ type: "validation_failed" }, fields)).toEqual(invalid);
  });

  test("an error without a place is the form's, and one with a place no field has says it", () => {
    expect(
      refusalsOf({ type: "validation_failed", errors: [{ msg: "Stale!" }] }, fields)?.form,
    ).toEqual(["What was asked for isn't valid."]);
    expect(
      refusalsOf(
        { type: "validation_failed", errors: [{ loc: ["answer", "extra"], msg: "Stale!" }] },
        fields,
      )?.form,
    ).toEqual(["What was asked for isn't valid: answer.extra."]);
  });

  test("no words of the server's reach the reader, however they are made", () => {
    const hostile = `${String.fromCodePoint(0x202e)}<img src=x onerror=alert(1)>\npassword=hunter2${"x".repeat(5000)}`;
    const refused = refusalsOf(
      {
        type: "validation_failed",
        message: hostile,
        errors: [
          { loc: ["email"], type: "value_error", msg: hostile },
          { loc: [hostile], msg: hostile },
          { loc: ["deep", hostile, "path"], msg: hostile },
        ],
      },
      fields,
    );
    const said = JSON.stringify(refused);
    for (const part of ["hunter2", "img", "onerror", String.fromCodePoint(0x202e), "xxxx"]) {
      expect(said).not.toContain(part);
    }
    expect(refused?.form).toEqual(["What was asked for isn't valid."]);
  });

  test.each([null, "refused", { type: "invalid_state", message: "answered" }])(
    "another rejection, %j, isn't one to put under fields",
    (rejection) => {
      expect(refusalsOf(rejection, fields)).toBeNull();
    },
  );
});

/** Parsed as the wire's JSON is, so a property named `__proto__` is a property, not a prototype. */
const FORMS = JSON.parse(
  FORMS_JSON,
) as typeof import("../../../../artifactr/tests/ui/vectors/forms.json");

// The forms artifactr.ui accepts and refuses values of, from the vectors it commits.
describe("the package's vectors", () => {
  const forms = FORMS.forms.map((form) => {
    const read = readSchema(form.schema);
    return { ...form, fields: read === null ? null : layoutOf(read, null).fields };
  });

  test.each(FORMS.refused_schemas)(
    "a schema the subset refuses, for $names, is none",
    ({ schema }) => {
      expect(readSchema(schema)).toBeNull();
    },
  );

  test.each(forms)("$name is a form this can show", ({ fields }) => {
    expect(fields).not.toBeNull();
  });

  test.each(
    forms.flatMap(({ name, fields, accepted }) =>
      accepted.map((values) => ({ name, fields, values })),
    ),
  )("$name accepts $values", ({ fields, values }) => {
    expect(problemsOf(fields ?? [], values)).toEqual({});
  });

  test.each(
    forms.flatMap(({ name, fields, refused }) =>
      refused.map((each) => ({ name, fields, ...each })),
    ),
  )("$name refuses $values at $loc", ({ fields, values, loc }) => {
    expect(Object.keys(problemsOf(fields ?? [], values))).toContain(String(loc[0] ?? ""));
  });
});

test.each([
  [{ type: "integer", minimum: 1, maximum: 30 }, "From 1 to 30."],
  [{ type: "number", minimum: 0.5 }, "0.5 or more."],
  [{ type: "number", maximum: 1500 }, "Up to 1,500."],
  [{ type: "number" }, null],
  [{ type: "array", items: { enum: ["a"] }, minItems: 2, maxItems: 2 }, "Choose 2."],
  [{ type: "array", items: { enum: ["a"] }, minItems: 1, maxItems: 3 }, "Choose 1 to 3."],
  [{ type: "array", items: { enum: ["a"] }, minItems: 1 }, "Choose 1 or more."],
  [{ type: "array", items: { enum: ["a"] }, maxItems: 2 }, "Choose up to 2."],
  [{ type: "array", items: { enum: ["a"] } }, null],
  [{ type: "string", maxLength: 80 }, "Up to 80 characters."],
  [{ type: "string", enum: ["a"], maxLength: 1 }, null],
  [{ type: "string" }, null],
  [{ type: "boolean" }, null],
] as const)("what %j allows is said before anything is entered: %s", (property, said) => {
  expect(limitsOf(fieldOf(property as Property))).toBe(said);
});

test.each([
  [{ type: "invalid_state", message: "already answered" }, { reason: "answered" }],
  [{ type: "invalid_state", reason: "changed", version: 1, head: 2 }, { reason: "changed" }],
  [{ type: "invalid_state", reason: "closed" }, { reason: "closed" }],
  [
    { type: "not_enabled", integration: "ui:dashboards" },
    { reason: "off", integration: "ui:dashboards" },
  ],
  [{ type: "invalid_state", reason: "off" }, null],
  [{ type: "not_enabled" }, null],
  [{ type: "invalid_state", reason: "frozen" }, null],
  [{ type: "validation_failed" }, null],
  [null, null],
])("an invalid state's reason, %j, is %j, never read from its message", (rejection, ended) => {
  expect(endedBy(rejection)).toEqual(ended);
});

describe("what is sent, as the package takes it", () => {
  test("a required set of choices left empty is sent empty; an optional one is left out", () => {
    const tags: Property = { type: "array", items: { enum: ["a"] } };
    expect(valuesOf([fieldOf(tags, true)], { it: [] })).toEqual({
      values: { it: [] },
      problems: {},
      whole: null,
    });
    expect(valuesOf([fieldOf(tags)], { it: [] }).values).toEqual({});
  });

  test("a text area's text is sent as written; a line is trimmed; white space alone is none", () => {
    expect(
      valuesOf([fieldOf({ type: "string" }, false, "textarea")], { it: "  two\nlines " }).values,
    ).toEqual({
      it: "  two\nlines ",
    });
    expect(valuesOf([fieldOf({ type: "string" })], { it: "  one  " }).values).toEqual({
      it: "one",
    });
    expect(problem(fieldOf({ type: "string" }, true, "textarea"), "   ")).toBe("Enter an answer.");
  });

  test.each(["0x10", "0b1", "0o7", "1e", "", "1,5", "Infinity"])("%j is no number", (entry) => {
    const field = fieldOf({ type: "number" }, true);
    expect(problem(field, entry)).toBe("Enter a number.");
  });

  test.each([
    ["12", 12],
    ["-1.5", -1.5],
    ["+3", 3],
    [".5", 0.5],
    ["2e3", 2000],
  ])("%j is the number %d", (entry, value) => {
    expect(valuesOf([fieldOf({ type: "number" })], { it: entry }).values).toEqual({ it: value });
  });

  test("answers weighing more than 64 KB are refused as a whole", () => {
    const field = fieldOf({ type: "string" }, false, "textarea");
    const many = layoutOf(
      schema(
        Object.fromEntries(Array.from({ length: 8 }, (_, at) => [`t${at}`, { type: "string" }])),
      ),
      null,
    ).fields;
    const draft = Object.fromEntries(many.map((one) => [one.name, "é".repeat(5000)]));
    expect(valuesOf(many, draft).whole).toBe(
      "These answers are too long to send: shorten the longest.",
    );
    expect(valuesOf([field], { it: "short" }).whole).toBeNull();
  });
});

describe("formats, as the package checks them", () => {
  test.each([
    ["2026-10-17T23:59:59Z", null],
    ["2026-10-17t09:30:00z", null],
    ["2026-10-17T09:30:00.5+02:00", null],
    ["2026-10-17T24:00:00Z", "Enter a date and a time."],
    ["2026-10-17T09:60:00Z", "Enter a date and a time."],
    ["2026-10-17T09:30:60Z", "Enter a date and a time."],
    ["2026-10-17T09:30:00+24:00", "Enter a date and a time."],
    ["2026-10-17T09:30:00+02:60", "Enter a date and a time."],
    ["0000-01-01T00:00:00Z", "Enter a date and a time."],
    ["2026-02-30T00:00:00Z", "Enter a date and a time."],
  ])("a moment %j: %s", (moment, said) => {
    expect(problemsOf([fieldOf({ type: "string", format: "date-time" })], { it: moment })).toEqual(
      said === null ? {} : { it: said },
    );
  });

  test("a day from year 1, and none before", () => {
    const day = fieldOf({ type: "string", format: "date" });
    expect(problem(day, "0001-01-01")).toBeNull();
    expect(problem(day, "0000-01-01")).toBe("Enter a date.");
  });

  test("an address of 254 characters at most", () => {
    const email = fieldOf({ type: "string", format: "email" });
    const at = "@example.com";
    expect(
      problem(email, `${"a".repeat(64)}@${"b".repeat(63)}.${"c".repeat(63)}.${"d".repeat(58)}.com`),
    ).toBe("Enter an email address, such as name@example.com.");
    expect(problem(email, `ana${at}`)).toBeNull();
  });

  test("a date and time entered is read strictly, its seconds kept, its default's too", () => {
    expect(momentOf("2026-10-17T09:30:15")).toBe(new Date("2026-10-17T09:30:15").toISOString());
    expect(momentOf("2026-10-17 09:30")).toBeNull();
    expect(momentOf("Oct 17 2026")).toBeNull();
    expect(momentOf("0000-10-17T09:30")).toBeNull();
    const field = fieldOf({ type: "string", format: "date-time", default: "2026-10-17T09:30:15Z" });
    expect(draftOf([field]).it).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:15$/);
  });
});

describe("the reader holds to the subset", () => {
  test.each([
    ["a length that isn't whole", { type: "string", maxLength: 1.5 }],
    ["a length below 0", { type: "string", minLength: -1 }],
    ["a count below 0", { type: "array", items: { enum: ["a"] }, minItems: -1 }],
    ["items with another keyword", { type: "array", items: { enum: ["a"], pattern: "a" } }],
    ["items of another type", { type: "array", items: { type: "number", enum: ["a"] } }],
    ["a labelled choice with more", { type: "string", oneOf: [{ const: "a", title: "A", x: 1 }] }],
    ["a title that isn't words", { type: "string", title: 3 }],
    ["a description that isn't words", { type: "boolean", description: false }],
    ["a default it doesn't take", { type: "string", maxLength: 2, default: "long" }],
    ["a number's default outside it", { type: "integer", maximum: 3, default: 4 }],
    [
      "an array's default it doesn't offer",
      { type: "array", items: { enum: ["a"] }, default: ["b"] },
    ],
    ["a boolean's default that isn't one", { type: "boolean", default: "yes" }],
    ["a choice's default it doesn't offer", { enum: ["a"], default: "b" }],
    ["bounds that meet, one open", { type: "number", exclusiveMinimum: 2, maximum: 2 }],
    ["bounds that cross", { type: "number", minimum: 3, exclusiveMaximum: 1 }],
    [
      "more chosen once than offered",
      { type: "array", items: { enum: ["a"] }, uniqueItems: true, minItems: 2 },
    ],
  ])("%s is refused", (_, property) => {
    expect(readSchema({ properties: { it: property } })).toBeNull();
  });

  test.each([
    ["bounds that meet, both closed", { type: "number", minimum: 2, maximum: 2 }],
    [
      "more than offered, where a choice may come twice",
      { type: "array", items: { enum: ["a"] }, minItems: 2 },
    ],
    ["a default it takes", { type: "integer", minimum: 1, default: 3 }],
    [
      "an array's default",
      { type: "array", items: { oneOf: [{ const: "a", title: "A" }] }, default: ["a"] },
    ],
  ])("%s is read", (_, property) => {
    expect(readSchema({ properties: { it: property } })).not.toBeNull();
  });

  test.each([
    ["order that isn't names", { order: "a" }],
    ["sections that aren't a list", { sections: { title: "A" } }],
    ["a section without its names", { sections: [{ title: "A" }] }],
    ["a button's words that aren't words", { submit_label: 3 }],
    ["help that isn't words", { fields: { a: { help: 1 } } }],
    ["a widget it doesn't have", { fields: { a: { widget: "slider" } } }],
    ["hints with more", { fields: { a: { colour: "red" } } }],
  ])("hints with %s are none, and the form shows as its schema has it", (_, ui) => {
    const asked = readAskForm({
      title: "T",
      schema: { properties: { a: { type: "string" } } },
      ui,
    });
    expect(asked?.ui).toBeNull();
  });

  test("a hint naming what an object inherits is passed over", () => {
    const layout = layoutOf(schema({ a: { type: "string" } }), {
      order: ["constructor", "a"],
      fields: {},
    });
    expect(layout.fields.map((field) => field.name)).toEqual(["a"]);
    expect(problemsOf(layout.fields, { a: "x" })).toEqual({});
  });
});

describe("the server's errors, in the kit's words", () => {
  const fields = layoutOf(
    schema(
      {
        mail: { type: "string", format: "email" },
        size: { type: "string", enum: ["S"] },
        tags: { type: "array", items: { enum: ["a"] } },
      },
      ["size"],
    ),
    null,
  ).fields;

  test.each([
    [{ loc: ["size"], type: "missing", msg: "Field required" }, "size", "Choose one."],
    [
      { loc: ["mail"], type: "format", msg: "Input should be a valid email" },
      "mail",
      "Enter an email address, such as name@example.com.",
    ],
    [
      { loc: ["size"], type: "enum", msg: "Input should be one of S" },
      "size",
      "Choose one of these.",
    ],
    [{ loc: ["tags"], type: "enum", msg: "b not among a" }, "tags", "Choose among these."],
    [{ loc: ["size"], type: "format", msg: "odd" }, "size", "This isn't valid."],
    [{ loc: ["mail"], type: "string_too_long", msg: "too long" }, "mail", "This isn't valid."],
  ])("%j is said under %s as %j", (error, name, said) => {
    expect(refusalsOf({ type: "validation_failed", errors: [error] }, fields)?.fields).toEqual({
      [name]: said,
    });
  });

  test("a missing field's error that names none is the form's", () => {
    expect(
      refusalsOf(
        { type: "validation_failed", errors: [{ loc: [], type: "missing", msg: "gone" }] },
        fields,
      )?.form,
    ).toEqual(["What was asked for isn't valid."]);
  });
});
