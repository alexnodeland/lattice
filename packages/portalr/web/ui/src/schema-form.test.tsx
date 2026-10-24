import { expect, onTestFinished, test, vi } from "vitest";
import { commands, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import type { FormSchema } from "./artifactr-ui";
import { SchemaForm } from "./schema-form";
import { contrast, token } from "./test/colours";
import { BUTTON, LEAVE, LEAVE_UI } from "./test/forms";
import { choose } from "./test/select";

type Outcome = Awaited<ReturnType<Parameters<typeof SchemaForm>[0]["onSubmit"]>>;

/** A submit handler whose sends end as `settled`. */
const answering = (settled: Outcome = { outcome: "done" }) => vi.fn(async () => settled);

/** The leave form, rendered, with a handler. */
async function leave(onSubmit = answering(), more: Partial<Parameters<typeof SchemaForm>[0]> = {}) {
  return render(
    <SchemaForm title="Request leave" schema={LEAVE} ui={LEAVE_UI} onSubmit={onSubmit} {...more} />,
  );
}

test("each property is the catalogue's control, named by its title, required ones said so", async () => {
  const screen = await leave();
  const form = screen.getByRole("form", { name: "Request leave" });
  await expect.element(form.getByRole("heading", { name: "Request leave" })).toBeVisible();
  await expect.element(form.getByText("Your manager sees what you send.")).toBeVisible();
  await expect.element(form.getByLabelText("First day (required)")).toHaveAttribute("type", "date");
  await expect
    .element(form.getByRole("textbox", { name: "Working days (required)" }))
    .toHaveAttribute("inputmode", "numeric");
  await expect
    .element(form.getByRole("radiogroup", { name: "Kind of leave (required)" }))
    .toBeVisible();
  await expect.element(form.getByRole("radio", { name: "Sick" })).not.toBeChecked();
  await expect
    .element(form.getByRole("combobox", { name: "Who covers" }))
    .toHaveTextContent("None");
  await expect
    .element(form.getByRole("textbox", { name: "Email while away" }))
    .toHaveAttribute("type", "email");
  await expect.element(form.getByRole("group", { name: "Handed over" })).toBeVisible();
  await expect.element(form.getByRole("switch", { name: "Tell the team today" })).not.toBeChecked();
  const note = form.getByRole("textbox", { name: "Anything else" });
  await expect.element(note).toHaveAttribute("placeholder", "A line for the team");
  expect(note.element().tagName).toBe("TEXTAREA");
  await expect.element(form.getByRole("group", { name: "While you're away" })).toBeVisible();
  await expect.element(form.getByRole("button", { name: "Ask for leave" })).toBeVisible();
});

test("a field is described by its description, its help and what it allows", async () => {
  const screen = await leave();
  await expect
    .element(screen.getByRole("textbox", { name: /Email while away/ }))
    .toHaveAccessibleDescription("Leave it empty to stay offline.");
  await expect
    .element(screen.getByRole("textbox", { name: /Working days/ }))
    .toHaveAccessibleDescription("From 1 to 30.");
  await expect
    .element(screen.getByRole("textbox", { name: /Anything else/ }))
    .toHaveAccessibleDescription("Up to 500 characters.");
});

test("what was entered is sent as values: empty fields left out, numbers as numbers", async () => {
  const onSubmit = answering();
  const screen = await leave(onSubmit);
  await screen.getByLabelText(/First day/).fill("2026-11-02");
  await screen.getByRole("textbox", { name: /Working days/ }).fill("3");
  await screen.getByRole("radio", { name: "Annual" }).click();
  await choose(screen, /Who covers/, "Carol");
  await screen.getByRole("checkbox", { name: "Reviews" }).click();
  await screen.getByRole("switch", { name: /Tell the team/ }).click();
  await screen.getByRole("textbox", { name: /Anything else/ }).fill("Back on the 5th.");
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
    starts: "2026-11-02",
    days: 3,
    kind: "annual",
    cover: "Carol",
    handover: ["Reviews"],
    urgent: true,
    note: "Back on the 5th.",
  });
  await expect.element(screen.getByRole("status")).toHaveTextContent("Sent.");
  await expect
    .element(screen.getByRole("button", { name: "Ask for leave" }))
    .not.toBeInTheDocument();
});

test("what the form refuses is said under each field, announced, and the focus moves to the first", async () => {
  const onSubmit = answering();
  const screen = await leave(onSubmit);
  await screen.getByRole("textbox", { name: /Email while away/ }).fill("alice@");
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  expect(onSubmit).not.toHaveBeenCalled();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("4 answers need a change: each says why under it.");
  const first = screen.getByLabelText(/First day/);
  await expect.element(first).toHaveFocus();
  await expect.element(first).toHaveAttribute("aria-invalid", "true");
  await expect.element(first).toHaveAccessibleDescription("Enter a date.");
  await expect
    .element(screen.getByRole("radiogroup", { name: /Kind of leave/ }))
    .toHaveAccessibleDescription("Choose one.");
  await expect
    .element(screen.getByRole("textbox", { name: /Email while away/ }))
    .toHaveAccessibleDescription(/Enter an email address, such as name@example.com\./);
});

test("a field changed since it was refused is no longer marked; the summary stays as it was said", async () => {
  const screen = await leave();
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  const alert = screen.getByRole("alert");
  await expect.element(alert).toHaveTextContent("3 answers need a change: each says why under it.");
  const days = screen.getByRole("textbox", { name: /Working days/ });
  await expect.element(days).toHaveAttribute("aria-invalid", "true");
  await days.fill("2");
  await expect.element(days).not.toHaveAttribute("aria-invalid");
  // Announced once a send: what it says changes only when the form is sent again.
  await expect.element(alert).toHaveTextContent("3 answers need a change: each says why under it.");
});

test("typing in a field refused after the first keeps the focus there", async () => {
  const screen = await leave();
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  await expect.element(screen.getByLabelText(/First day/)).toHaveFocus();
  const days = screen.getByRole("textbox", { name: /Working days/ });
  await days.click();
  await userEvent.keyboard("12");
  await expect.element(days).toHaveFocus();
  await expect.element(days).toHaveValue("12");
});

test("the form read again, as a refetch does, doesn't move the focus", async () => {
  const onSubmit = answering();
  const screen = await leave(onSubmit);
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  const days = screen.getByRole("textbox", { name: /Working days/ });
  await days.click();
  await screen.rerender(
    <SchemaForm
      title="Request leave"
      schema={{ ...LEAVE }}
      ui={{ ...LEAVE_UI }}
      onSubmit={onSubmit}
    />,
  );
  await expect.element(days).toHaveFocus();
});

test("answers too long to send are refused as a whole", async () => {
  const onSubmit = answering();
  const names = ["a", "b", "c", "d", "e", "f", "g"];
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: Object.fromEntries(
          names.map((name) => [name, { type: "string", title: name }]),
        ),
      }}
      onSubmit={onSubmit}
    />,
  );
  for (const name of names) {
    // 5,000 characters of two bytes each: 70,000 bytes in all, over the package's 64 KB.
    await screen.getByRole("textbox", { name, exact: true }).fill("é".repeat(5000));
  }
  await screen.getByRole("button", { name: "Send" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("These answers are too long to send: shorten the longest.");
  expect(onSubmit).not.toHaveBeenCalled();
});

test("one refusal is said in the singular", async () => {
  const screen = await render(
    <SchemaForm
      schema={{ type: "object", properties: { a: { type: "string" } }, required: ["a"] }}
      onSubmit={answering()}
    />,
  );
  await screen.getByRole("button", { name: "Send" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("One answer needs a change: each says why under it.");
});

test("a required group of a few choices, none chosen, takes the focus on its first when refused", async () => {
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: { size: { type: "string", title: "Size", enum: ["S", "M", "L"] } },
        required: ["size"],
      }}
      onSubmit={answering()}
    />,
  );
  await expect.element(screen.getByRole("radio", { name: "S" })).not.toBeChecked();
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByRole("radio", { name: "S" })).toHaveFocus();
});

test("a group's refusal moves the focus to its first choice", async () => {
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: { tags: { type: "array", items: { enum: ["x", "y"] }, minItems: 1 } },
        required: ["tags"],
      }}
      onSubmit={answering()}
    />,
  );
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByRole("checkbox", { name: "x" })).toHaveFocus();
  await expect
    .element(screen.getByRole("group", { name: /tags/ }))
    .toHaveAccessibleDescription("Choose 1 or more. Choose 1 or more.");
});

const EMAIL: FormSchema = {
  type: "object",
  properties: { email: { type: "string", title: "Email" }, age: { type: "integer" } },
};

test("the server's refusal is put under the fields it names, and what names none above them", async () => {
  const onSubmit = answering({
    outcome: "refused",
    result: {
      rejection: {
        type: "validation_failed",
        message: "values are invalid",
        errors: [
          { loc: ["answer", "email"], msg: "value is not a valid email address" },
          { loc: ["form"], msg: "the form is closed" },
        ],
      },
    },
  });
  const screen = await render(<SchemaForm schema={EMAIL} onSubmit={onSubmit} />);
  await screen.getByRole("textbox", { name: "Email" }).fill("someone");
  await screen.getByRole("button", { name: "Send" }).click();
  const email = screen.getByRole("textbox", { name: "Email" });
  await expect.element(email).toHaveFocus();
  await expect.element(email).toHaveAccessibleDescription("This isn't valid.");
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent(
      "One answer needs a change: each says why under it.What was asked for isn't valid.",
    );
});

test("a refusal that names no field says why, above the fields", async () => {
  const onSubmit = answering({
    outcome: "refused",
    result: { rejection: { type: "validation_failed", message: "too many values" } },
  });
  const screen = await render(<SchemaForm schema={EMAIL} onSubmit={onSubmit} />);
  await screen.getByRole("button", { name: "Send" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("What was asked for isn't valid.");
  expect(screen.getByText(/too many values/i).elements()).toHaveLength(0);
});

test.each([
  [
    "refused otherwise",
    { outcome: "refused", result: { rejection: { type: "not_found" } } },
    "That wasn't done: the server refused it.",
  ],
  ["not sent", { outcome: "closed" }, "That wasn't sent: the connection closed."],
] as const)("a form %s says why, and can be sent again", async (_, settled, said) => {
  const onSubmit = answering(settled as Outcome);
  const screen = await render(
    <SchemaForm schema={BUTTON} ui={{ submit_label: "Ship it" }} onSubmit={onSubmit} />,
  );
  await screen.getByRole("button", { name: "Ship it" }).click();
  await expect.element(screen.getByRole("alert")).toHaveTextContent(said);
  await screen.getByRole("button", { name: "Ship it" }).click();
  expect(onSubmit).toHaveBeenCalledTimes(2);
});

test("a form waits for its send, and isn't sent twice meanwhile", async () => {
  let settle: (settled: Outcome) => void = () => undefined;
  const onSubmit = vi.fn(
    () =>
      new Promise<Outcome>((done) => {
        settle = done;
      }),
  );
  const screen = await render(<SchemaForm schema={BUTTON} onSubmit={onSubmit} />);
  const button = screen.getByRole("button", { name: "Send" });
  await button.click();
  await expect.element(button).toBeDisabled();
  button.element().closest("form")?.requestSubmit();
  expect(onSubmit).toHaveBeenCalledTimes(1);
  settle({ outcome: "done" });
  await expect.element(screen.getByRole("status")).toHaveTextContent("Sent.");
});

test("a form of no fields is its button, named by its title's words", async () => {
  const onSubmit = answering();
  const screen = await render(
    <SchemaForm title="Ready to ship?" schema={BUTTON} onSubmit={onSubmit} />,
  );
  const form = screen.getByRole("form", { name: "Ready to ship?" });
  await expect.element(form.getByRole("textbox")).not.toBeInTheDocument();
  await form.getByRole("button", { name: "Ready to ship?" }).click();
  expect(onSubmit).toHaveBeenCalledWith({});
});

test("a form without a title is named by its button", async () => {
  const screen = await render(
    <SchemaForm schema={BUTTON} ui={{ submit_label: "Agree" }} onSubmit={answering()} />,
  );
  await expect.element(screen.getByRole("form", { name: "Agree" })).toBeVisible();
  await expect.element(screen.getByRole("heading")).not.toBeInTheDocument();
});

test("once sent, another can be sent, from the fields' defaults", async () => {
  const onAnother = vi.fn();
  const onSubmit = answering();
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: { n: { type: "string", title: "Name", default: "x" } },
      }}
      onSubmit={onSubmit}
      onAnother={onAnother}
    />,
  );
  await screen.getByRole("textbox", { name: "Name" }).fill("Bob");
  await screen.getByRole("button", { name: "Send" }).click();
  await screen.getByRole("button", { name: "Send another" }).click();
  expect(onAnother).toHaveBeenCalledOnce();
  await expect.element(screen.getByRole("textbox", { name: "Name" })).toHaveValue("x");
});

test("a form that ended says why in place of its fields; a notice sits above them", async () => {
  const ended = await render(
    <SchemaForm schema={LEAVE} onSubmit={answering()} ended={<p>This form is closed.</p>} />,
  );
  await expect.element(ended.getByText("This form is closed.")).toBeVisible();
  await expect.element(ended.getByRole("button")).not.toBeInTheDocument();
  const noticed = await render(
    <SchemaForm schema={BUTTON} onSubmit={answering()} notice={<p>This form changed.</p>} />,
  );
  await expect.element(noticed.getByText("This form changed.")).toBeVisible();
  await expect.element(noticed.getByRole("button", { name: "Send" })).toBeVisible();
});

test("locked, its fields stay as entered and can't be changed, and it has no button", async () => {
  const screen = await leave(answering(), { locked: <p>Forms are off.</p> });
  await expect.element(screen.getByText("Forms are off.")).toBeVisible();
  await expect.element(screen.getByLabelText(/First day/)).toBeDisabled();
  await expect.element(screen.getByRole("radio", { name: "Sick" })).toBeDisabled();
  await expect.element(screen.getByRole("combobox", { name: /Who covers/ })).toBeDisabled();
  await expect.element(screen.getByRole("checkbox", { name: "Reviews" })).toBeDisabled();
  await expect.element(screen.getByRole("switch", { name: /Tell the team/ })).toBeDisabled();
  await expect.element(screen.getByRole("textbox", { name: /Anything else/ })).toBeDisabled();
  await expect
    .element(screen.getByRole("button", { name: "Ask for leave" }))
    .not.toBeInTheDocument();
});

test("asked to, it takes the focus on its first field as it appears, else on its button", async () => {
  const screen = await leave(answering(), { autoFocus: true });
  await expect.element(screen.getByLabelText(/First day/)).toHaveFocus();
  const button = await render(<SchemaForm schema={BUTTON} onSubmit={answering()} autoFocus />);
  await expect.element(button.getByRole("button", { name: "Send" })).toHaveFocus();
});

test("the keyboard fills it in and sends it: Tab between fields, arrows in a group, Space, Enter", async () => {
  const onSubmit = answering();
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: {
          size: { type: "string", title: "Size", enum: ["S", "M", "L"], default: "S" },
          gift: { type: "boolean", title: "Gift" },
          name: { type: "string", title: "Name" },
        },
      }}
      onSubmit={onSubmit}
    />,
  );
  await userEvent.tab();
  await expect.element(screen.getByRole("radio", { name: "S" })).toHaveFocus();
  await userEvent.keyboard("{ArrowRight}");
  await expect.element(screen.getByRole("radio", { name: "M" })).toBeChecked();
  await userEvent.tab();
  await expect.element(screen.getByRole("switch", { name: "Gift" })).toHaveFocus();
  await userEvent.keyboard(" ");
  await userEvent.tab();
  await userEvent.keyboard("Ann{Enter}");
  expect(onSubmit).toHaveBeenCalledWith({ size: "M", gift: true, name: "Ann" });
});

test("a box asked for by its hint is a checkbox, toggled as one", async () => {
  const onSubmit = answering();
  const screen = await render(
    <SchemaForm
      schema={{ type: "object", properties: { ok: { type: "boolean", title: "I agree" } } }}
      ui={{ fields: { ok: { widget: "checkbox" } } }}
      onSubmit={onSubmit}
    />,
  );
  await screen.getByRole("checkbox", { name: "I agree" }).click();
  await screen.getByRole("button", { name: "Send" }).click();
  expect(onSubmit).toHaveBeenCalledWith({ ok: true });
});

test("a toggle's hint describes it", async () => {
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: { ok: { type: "boolean", title: "Notify", description: "By email." } },
      }}
      onSubmit={answering()}
    />,
  );
  await expect
    .element(screen.getByRole("switch", { name: "Notify" }))
    .toHaveAccessibleDescription("By email.");
});

test("a date and time is entered in the reader's zone and sent in UTC", async () => {
  const onSubmit = answering();
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: { at: { type: "string", format: "date-time", title: "When" } },
      }}
      onSubmit={onSubmit}
    />,
  );
  const when = screen.getByLabelText("When");
  await expect.element(when).toHaveAttribute("type", "datetime-local");
  await when.fill("2026-10-17T09:30");
  await screen.getByRole("button", { name: "Send" }).click();
  expect(onSubmit).toHaveBeenCalledWith({ at: new Date("2026-10-17T09:30").toISOString() });
});

test("an optional select starts on None, a required one asks to choose, and a number takes decimals", async () => {
  const screen = await render(
    <SchemaForm
      schema={{
        type: "object",
        properties: {
          pick: { type: "string", title: "Pick", enum: ["a", "b"] },
          must: { type: "string", title: "Must", enum: ["a", "b"] },
          rate: { type: "number", title: "Rate" },
          site: { type: "string", title: "Site", format: "uri" },
        },
        required: ["must"],
      }}
      ui={{ fields: { must: { widget: "select" } } }}
      onSubmit={answering()}
    />,
  );
  await expect.element(screen.getByRole("combobox", { name: "Pick" })).toHaveTextContent("None");
  await expect
    .element(screen.getByRole("combobox", { name: /Must/ }))
    .toHaveTextContent("Choose one…");
  await expect
    .element(screen.getByRole("textbox", { name: "Rate" }))
    .toHaveAttribute("inputmode", "decimal");
  await expect
    .element(screen.getByRole("textbox", { name: "Site" }))
    .toHaveAttribute("type", "url");
});

test("its words read in the scheme: the title, the required mark and a refusal", async () => {
  const screen = await leave();
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  const surface = token("paper");
  for (const words of [
    screen.getByRole("heading", { name: "Request leave" }),
    screen.getByText("(required)").first(),
    screen.getByText("Enter a date."),
  ]) {
    const style = getComputedStyle(words.element());
    expect(contrast(style.color, surface)).toBeGreaterThanOrEqual(4.5);
  }
});

test("under forced colours and in colour-blind mode, the form keeps its words and its marks", async () => {
  onTestFinished(() => commands.forcedColors(false));
  document.documentElement.dataset.cvd = "";
  onTestFinished(() => {
    delete document.documentElement.dataset.cvd;
  });
  const screen = await leave();
  await screen.getByRole("button", { name: "Ask for leave" }).click();
  await commands.forcedColors(true);
  await expect.element(screen.getByText("Enter a date.")).toBeVisible();
  await expect.element(screen.getByText("(required)").first()).toBeVisible();
  // The refused field's edge is the text's colour, which forced colours keep as a line.
  const first = getComputedStyle(screen.getByLabelText(/First day/).element());
  expect(first.borderTopStyle).toBe("solid");
  expect(first.borderTopWidth).toBe("1px");
});
