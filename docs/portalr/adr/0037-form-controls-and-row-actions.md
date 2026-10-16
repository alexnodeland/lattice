# ADR-0037: Form controls and row actions: a Base UI select, form fields, segmented windows, button variants and sizes

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland
**Amends:** the controls and buttons of [ADR-0019](0019-the-kits-look.md)

## Context

The UI polish pass (issue 214) found the form controls the loudest mismatch with the kit:

- Every choice was a native `<select>`, full width in its form, drawn by the platform, beside the switcher, which is Base UI's menu.
- A window of hours or days, a handful of choices, was a drop-down, which hides the choices it was there to show.
- Eight outlined "Remove" buttons in a table were as loud as the primary action. Retry, Skip and Cancel looked alike, and a disabled button looked like a secondary one.
- The confirmation of cancelling a run put a "Cancel" beside "Cancel the run".

## Decision

- **`SelectField` is Base UI's Select,** on the surface menus float on (`popover`), its trigger with a control's edge and height and a chevron, as the switcher's has. It keeps what a native select gave: it is named by its label, starts on its first choice, submits with its form by `name`, takes `required` and `disabled`, and its keyboard works as a native one's: arrow keys move through the choices, a letter finds one, Enter chooses it, and Escape closes the list and gives the focus back to the trigger. The tests hold each, in both schemes. Its role is still `combobox`, named by its label, so `getByRole("combobox", { name })` finds it as ever; choosing is now by opening it and picking an `option`, which `ui/testing`'s `choose` and `optionsOf` do for tests, and which the BDD steps do beside them.
- **`FormField` is the frame of every control:** its label, the control, a hint under it, and why it was refused. Base UI's Field names the control by the label and describes it by the hint and the error. A field is no wider than 28rem (`max-w-md`) however wide its form. `TextField` and `SelectField` are built on it.
- **A window is a `SegmentedFilter`,** not a select: Feedback's and Usage's days, Logs' and Traces' hours, Health's, and Runs' "Show". Its label and a hint are written above and under it (`showLabel`, `hint`), and with `name` it submits with a form, as Logs' and Traces' do. A set of more than a few, such as the workspaces, stays a select. Its labels are short ("30 days"), and what they hold in common ("Whole days, in UTC.") is its hint.
- **A button has a variant and a size.** The variants are `primary`, `secondary`, `ghost`, `danger-soft` (a destructive action offered, in the danger colour on a wash of it) and `danger` (the same, confirmed, solid); the sizes are `md` and `sm`. A disabled button is on a muted fill (`--line`) in the quiet text, with the cursor that says it can't be used, so it differs from a secondary one without fading: its words stay 4.5:1 on it, which the tests hold.
- **A row's action is small, ghost, and says only its verb.** `ConfirmDialog` takes `look`, `size` and `about`: a row shows "Revoke", and "alice (person) as owner", what it acts on, is read aloud by a visually hidden span after it, so the accessible name is whole and a voice control finds the visible word. A destructive row action is `danger-soft` (Remove, Revoke, Delete); Retry and Skip are `ghost`, and Cancel a run is `danger-soft`, so it is visibly destructive.
- **A dialog's way out has words of its own where "Cancel" would stand beside another:** `dismiss`. Cancelling a run is "Keep running" and "Cancel run". Elsewhere it is "Cancel", and the focus starts on it as before.
- **Row heights don't change here.** Admin's compact density is a later change of its own.
- **Motion and the colour-blind mode need nothing new:** the controls take their colours from tokens only, and the list's open and close are Base UI's, with `motion-reduce` honoured as the menus' are.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Select | **Base UI Select (chosen)** | The kit's look and surface; one Field around every control | The platform's picker on a phone is lost; a test chooses by clicking |
| | The native select, styled | The platform's picker on a phone | Its list can't be styled, so it stays the mismatch |
| Windows | **A segmented filter (chosen)** | Every choice seen at once, one click | Only for a few choices |
| | A select | One control for every set | Hides the choices |
| Row actions | **Small ghost, verb alone, name aloud (chosen)** | A quiet row that reads whole | Two pieces of text in a button |
| | Outlined buttons with the id in their words | The name is plain | Eight alike, as loud as the primary |
| A confirmation's way out | **Words of its own where it would clash (chosen)** | "Keep running" says what it keeps | A prop |
| | "Cancel" always | One word everywhere | "Cancel" beside "Cancel the run" |

## Consequences

- Easier: a new form takes `FormField`, `SelectField` and `SegmentedFilter` and looks like the rest; a test chooses with one helper.
- Harder: a select's choices exist only while it is open, so a test that reads them opens it first.
- To revisit: whether a phone should get the platform's picker for a long select; admin's compact density and the status colours, in their own changes.
