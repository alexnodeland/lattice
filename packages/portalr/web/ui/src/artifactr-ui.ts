/**
 * The wire shapes of artifactr.ui's artifacts, of an `ask_form` request and of its refusals
 * (lattice RFC-0005), as `client` generates them from the package's committed schema, under the
 * names `ui` uses: every other module names them from here.
 *
 * They say what the server sends, not what arrives: an artifact's data and a request's arguments
 * are any JSON at run time, so `form-schema.ts` and `dashboard-view.tsx` read them into these
 * shapes, and show what doesn't fit as such rather than throw. A read property always has its
 * `type`, which a choice may leave out on the wire.
 */

import type { ArtifactrUiV1 as V1 } from "@portalr/client";

/** A wire shape as it is read: a property the wire may send as null is left out instead. */
type Read<T> = { readonly [K in keyof T]: Exclude<T[K], null> };

/** A string property, choices included, as it is read: its `type` written. */
type StringProperty = Read<V1.StringProperty> & Read<Omit<V1.ChoiceProperty, "type">>;

/** An array of choices, as it is read: its items' `type`, always a string's, written or not. */
type ArrayProperty = Omit<Read<V1.ArrayProperty>, "items"> & {
  readonly items: Read<Omit<V1.Choices, "type">> & { readonly type?: "string" };
};

export type Property =
  | StringProperty
  | Read<V1.NumberProperty>
  | Read<V1.BooleanProperty>
  | ArrayProperty;

/**
 * A form's schema, as it is read: each property with its `type`, and `additionalProperties`, which
 * is false whether it is written or not.
 */
export type FormSchema = Omit<V1.FormSchema, "properties" | "additionalProperties"> & {
  readonly properties?: Readonly<Record<string, Property>>;
  readonly additionalProperties?: false;
};

export type PropertyHints = V1.FieldHints;
export type UiHints = V1.UiHints;

/** A `form` artifact, as it is read: its schema read, and how it takes submissions said. */
export type Form = Omit<V1.Form, "schema" | "submissions" | "closed"> & {
  readonly schema: FormSchema;
  readonly submissions: V1.Submissions;
  readonly closed: boolean;
};

/** An `ask_form` request's arguments, as they are read. */
export type AskForm = Omit<V1.FormRequest, "schema"> & { readonly schema: FormSchema };

/** A submitted value: what each kind of field gives. */
export type Value = string | number | boolean | string[];

/** A form's values, by property: a field left empty is left out. */
export type Values = Readonly<Record<string, Value>>;

export type Submission = V1.Submission;
export type StatPanel = V1.StatPanel;
export type Keyed = V1.Key;
export type DonutPart = V1.Part;
export type Row = V1.Rows[number];
export type TableRow = V1.Rows1[number];
export type TablePanel = V1.TablePanel;
export type Panel = V1.Panels[number];
/** A dashboard, as it is read: its panels listed, none if it has none. */
export type Dashboard = Omit<V1.Dashboard, "panels"> & { readonly panels: readonly Panel[] };
export type RefusalReason = V1.RefusalReason;

/** The most rows a table panel holds. */
export const MAX_TABLE_ROWS = 500;
