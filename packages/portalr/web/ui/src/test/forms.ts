/** Forms the tests and the screenshots share: one of every control, and one of none. */

import type { AskForm, FormSchema, UiHints } from "../artifactr-ui";

/** A request for leave: one of every control the catalogue has, in two sections. */
export const LEAVE: FormSchema = {
  type: "object",
  description: "Your manager sees what you send.",
  properties: {
    starts: { type: "string", format: "date", title: "First day" },
    days: { type: "integer", title: "Working days", minimum: 1, maximum: 30 },
    kind: {
      type: "string",
      title: "Kind of leave",
      oneOf: [
        { const: "annual", title: "Annual" },
        { const: "sick", title: "Sick" },
        { const: "unpaid", title: "Unpaid" },
      ],
    },
    cover: {
      type: "string",
      title: "Who covers",
      enum: ["Alice", "Bob", "Carol", "Dan", "Erin", "Frank"],
    },
    email: { type: "string", format: "email", title: "Email while away" },
    note: { type: "string", title: "Anything else", maxLength: 500 },
    handover: {
      type: "array",
      title: "Handed over",
      items: { enum: ["On-call", "Reviews", "Releases"] },
    },
    urgent: { type: "boolean", title: "Tell the team today" },
  },
  required: ["starts", "days", "kind"],
};

export const LEAVE_UI: UiHints = {
  fields: {
    note: { widget: "textarea", placeholder: "A line for the team" },
    email: { help: "Leave it empty to stay offline." },
  },
  sections: [
    { title: "While you're away", properties: ["cover", "email", "handover", "urgent", "note"] },
  ],
  submit_label: "Ask for leave",
};

/** The leave form as an `ask_form` request's arguments. */
export const ASK_LEAVE: AskForm = { title: "Request leave", schema: LEAVE, ui: LEAVE_UI };

/** A form with no fields: a button. */
export const BUTTON: FormSchema = { type: "object" };
