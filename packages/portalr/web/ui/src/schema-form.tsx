/**
 * A form an agent wrote, as data, shown with the kit's own controls (lattice RFC-0005): each
 * property of its schema a field, by the RFC's catalogue, in its hints' order and sections. What a
 * person enters is checked as the server will check it before it is sent, and what either refuses
 * is said under its field, through `FormField`, with the focus moved to the first. A form with no
 * fields is its button.
 */

import { type FormEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { Alert } from "./alert";
import type { FormSchema, UiHints, Values } from "./artifactr-ui";
import { Button } from "./button";
import { Checkbox, CheckboxGroup } from "./checkbox";
import { cn } from "./cn";
import { FormField } from "./form-field";
import {
  type Draft,
  draftOf,
  type Field as FormFieldShape,
  layoutOf,
  limitsOf,
  refusalsOf,
  valuesOf,
} from "./form-schema";
import { own } from "./json";
import { SegmentedFilter } from "./segmented-filter";
import { SelectField } from "./select-field";
import { type Sent, Unsent, useSending } from "./sending";
import { Switch } from "./switch";
import { TextArea } from "./text-area";
import { TextField } from "./text-field";
import { TYPE } from "./type";

/** A field's name, and that it must be filled in, said in words: "Email (required)". */
function Label({ field }: { field: FormFieldShape }) {
  return (
    <>
      {field.label}
      {field.required && <span className="font-normal text-muted"> (required)</span>}
    </>
  );
}

/** What is said under a field: its property's description, its hint's help, then what it allows. */
const hintOf = (field: FormFieldShape) =>
  [field.description, field.help, limitsOf(field)].filter(Boolean).join(" ") || undefined;

/** The input type a text field takes, by its control. */
const INPUT = {
  text: "text",
  email: "email",
  uri: "url",
  date: "date",
  "date-time": "datetime-local",
  number: "text",
} as const;

/**
 * A yes or no, its words beside it: a switch or a box, with its hint and refusal under them, as a
 * field's.
 */
function Toggle({
  field,
  on,
  error,
  disabled,
  onChange,
}: {
  field: FormFieldShape;
  on: boolean;
  error: string | null;
  disabled: boolean;
  onChange: (on: boolean) => void;
}) {
  const control =
    field.control === "switch" ? (
      <Switch checked={on} onCheckedChange={onChange} disabled={disabled} />
    ) : (
      <Checkbox checked={on} onCheckedChange={onChange} disabled={disabled} />
    );
  return (
    <FormField label={<Label field={field} />} hint={hintOf(field)} error={error} beside>
      {control}
    </FormField>
  );
}

/** One field, by its control, holding its entry in the draft. */
function Entry({
  field,
  entry,
  error,
  disabled,
  onChange,
}: {
  field: FormFieldShape;
  entry: string | boolean | readonly string[];
  error: string | null;
  /** Shown as entered, and not to be changed: the form can't be sent. */
  disabled: boolean;
  onChange: (entry: string | boolean | readonly string[]) => void;
}) {
  const label = <Label field={field} />;
  const hint = hintOf(field);
  const text = typeof entry === "string" ? entry : "";
  const placeholder = field.placeholder ?? undefined;
  switch (field.control) {
    case "switch":
    case "checkbox":
      return (
        <Toggle
          field={field}
          on={entry === true}
          error={error}
          disabled={disabled}
          onChange={onChange}
        />
      );
    case "checkboxes":
      return (
        <CheckboxGroup
          legend={label}
          choices={field.choices}
          value={Array.isArray(entry) ? entry : []}
          onValueChange={onChange}
          hint={hint}
          error={error}
          disabled={disabled}
        />
      );
    case "segments":
      return (
        <SegmentedFilter
          label={label}
          showLabel
          segments={field.choices}
          value={text}
          onValueChange={onChange}
          hint={hint}
          error={error}
          disabled={disabled}
        />
      );
    case "select":
      return (
        <SelectField
          label={label}
          hint={hint}
          error={error}
          options={[
            { value: "", label: field.required ? "Choose one…" : "None" },
            ...field.choices,
          ]}
          value={text}
          onValueChange={onChange}
          disabled={disabled}
        />
      );
    case "textarea":
      return (
        <TextArea
          label={label}
          hint={hint}
          error={error}
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          onValueChange={(value) => onChange(String(value))}
        />
      );
    default:
      return (
        <TextField
          label={label}
          hint={hint}
          error={error}
          type={INPUT[field.control]}
          {...(field.control === "number" && {
            inputMode: field.property.type === "integer" ? "numeric" : "decimal",
          })}
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          onValueChange={(value) => onChange(String(value))}
        />
      );
  }
}

/** What the focus may land on in a field: its control, or a group's first choice it can reach. */
const FOCUSABLE =
  'input:not([type="hidden"]):not([aria-hidden="true"]), textarea, button:not([tabindex="-1"]), [role="radio"][tabindex="0"], [role="checkbox"]';

/** A send's refusal, as it was made: the first field refused, how many were, and what else was said. */
interface Refusal {
  readonly first: string | null;
  readonly count: number;
  readonly said: readonly string[];
}

/** Why the form wasn't sent, in a sentence: how many answers to change, and anything the server said of it alone. */
function Problems({ count, said }: { count: number; said: readonly string[] }) {
  return (
    <Alert tone="error">
      {count > 0 && (
        <p>
          {count === 1 ? "One answer needs a change" : `${count} answers need a change`}: each says
          why under it.
        </p>
      )}
      {said.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </Alert>
  );
}

/**
 * A form from its schema and hints: a field for each property, its title as its heading, and its
 * button. It checks what was entered before `onSubmit` sends the values, and puts the server's
 * refusal of them under the same fields. Once sent it says so, and, with `onAnother`, offers to
 * send another. `notice` is said above the fields, such as that the form changed; `ended` says why
 * it can't be sent any more, such as that it was answered, in place of its fields; `locked` says
 * why it can't be sent for now, such as that forms are off, above its fields, which stay as they
 * were entered but can't be changed, and it has no button.
 */
export function SchemaForm({
  title,
  schema,
  ui,
  onSubmit,
  notice,
  ended,
  locked,
  onAnother,
  autoFocus = false,
  className,
}: {
  /** Its heading, and its name; a form shown under its own page's title leaves it out. */
  title?: string;
  schema: FormSchema;
  ui?: UiHints | null | undefined;
  /** Send the values, as the person; the form says what the server answered. */
  onSubmit: (values: Values) => Sent;
  /** Said above the fields, which can still be sent. */
  notice?: ReactNode;
  /** Why it can't be sent any more, said in place of its fields and its button. */
  ended?: ReactNode;
  /** Why it can't be sent for now, said above its fields, which stay, unchangeable, without a button. */
  locked?: ReactNode;
  /** Offer to send another once it is sent, starting from the fields' defaults. */
  onAnother?: () => void;
  /** Take the focus as it appears, on its first field, or its button: a paused request does. */
  autoFocus?: boolean;
  className?: string;
}) {
  const heading = useId();
  const layout = useMemo(() => layoutOf(schema, ui, title), [schema, ui, title]);
  const [draft, setDraft] = useState<Draft>(() => draftOf(layout.fields));
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  // The last send's refusal, as it was made: its summary, and the field to move the focus to. A
  // new object for each refused send, so the focus moves once a send, never as a person types.
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const { pending, unsent, send, forget } = useSending();
  const [sent, setSent] = useState(false);
  const form = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (autoFocus) {
      form.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    }
  }, [autoFocus]);

  useEffect(() => {
    if (refusal?.first) {
      form.current
        ?.querySelector(`[data-field="${CSS.escape(refusal.first)}"]`)
        ?.querySelector<HTMLElement>(FOCUSABLE)
        ?.focus();
    }
  }, [refusal]);

  function refuse(problems: Readonly<Record<string, string>>, said: readonly string[]) {
    setErrors(problems);
    setRefusal({
      first: layout.fields.find((field) => Object.hasOwn(problems, field.name))?.name ?? null,
      count: Object.keys(problems).length,
      said: [...new Set(said)],
    });
  }

  function change(name: string, entry: string | boolean | readonly string[]) {
    setDraft((before) => ({ ...before, [name]: entry }));
    // A field changed since it was refused is no longer known to be wrong.
    setErrors((before) =>
      Object.fromEntries(Object.entries(before).filter(([key]) => key !== name)),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) {
      return;
    }
    const { values, problems, whole } = valuesOf(layout.fields, draft);
    forget();
    setRefusal(null);
    setErrors({});
    if (Object.keys(problems).length > 0 || whole !== null) {
      refuse(problems, whole === null ? [] : [whole]);
      return;
    }
    // A refusal of the values is said under their fields; anything else, under the button.
    const done = await send(
      () => onSubmit(values),
      ({ outcome, result }) => {
        const refusals =
          outcome === "refused" ? refusalsOf(result?.rejection, layout.fields) : null;
        if (refusals !== null) {
          refuse(refusals.fields, refusals.form);
        }
        return refusals !== null;
      },
    );
    setSent(done);
  }

  function another() {
    setDraft(draftOf(layout.fields));
    setSent(false);
    onAnother?.();
  }

  // Its fields show until it is sent or it ends; they can be changed and sent unless it is locked.
  const shown = ended === undefined && !sent;
  const open = shown && locked === undefined;
  return (
    <form
      ref={form}
      noValidate
      onSubmit={submit}
      aria-labelledby={title ? heading : undefined}
      aria-label={title ? undefined : layout.submitLabel}
      className={cn("flex flex-col gap-4", className)}
    >
      {(title || layout.description) && (
        <div className="flex flex-col gap-1">
          {title && (
            <h2 id={heading} className={TYPE.label}>
              {title}
            </h2>
          )}
          {layout.description && <p className={TYPE.meta}>{layout.description}</p>}
        </div>
      )}
      {shown && locked}
      {open && notice}
      {open && refusal && (Object.keys(errors).length > 0 || refusal.said.length > 0) && (
        <Problems count={refusal.count} said={refusal.said} />
      )}
      {shown &&
        layout.groups.map((group) => {
          const fields = group.fields.map((field) => (
            <div key={field.name} data-field={field.name} className="flex flex-col">
              <Entry
                field={field}
                entry={(own(draft, field.name) as Draft[string] | undefined) ?? ""}
                error={(own(errors, field.name) as string | undefined) ?? null}
                disabled={!open}
                onChange={(entry) => change(field.name, entry)}
              />
            </div>
          ));
          return group.title === null ? (
            <div key={group.key} className="flex flex-col gap-4">
              {fields}
            </div>
          ) : (
            <fieldset
              key={group.key}
              className="m-0 min-w-0 border-0 border-line border-t p-0 pt-4"
            >
              <legend className={cn(TYPE.labelQuiet, "float-left mb-3 w-full p-0")}>
                {group.title}
              </legend>
              <div className="clear-left flex flex-col gap-4">{fields}</div>
            </fieldset>
          );
        })}
      {open && (
        <div className="flex flex-col items-start gap-2">
          <Button type="submit" disabled={pending}>
            {layout.submitLabel}
          </Button>
          <Unsent reason={unsent} />
        </div>
      )}
      {ended}
      {ended === undefined && sent && (
        <div className="flex flex-col items-start gap-2">
          <Alert>Sent.</Alert>
          {onAnother && (
            <Button variant="secondary" onClick={another}>
              Send another
            </Button>
          )}
        </div>
      )}
    </form>
  );
}
