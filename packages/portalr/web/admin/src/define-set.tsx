/**
 * The form grantr's named sets share: a group's members and a custom role's actions. Each is
 * created under a name not yet taken, or changed from its row, starting from what grantr last
 * said; grantr replaces it whole, and a change that takes anything out is confirmed first, saying
 * what is lost (portalr ADR-0024, ADR-0025).
 */

import { type Answer, orThrow, refusal } from "@portalr/client";
import { Button, Card, CheckboxGroup, ConfirmDialog, SectionTitle, TextField } from "@portalr/ui";
import { type ReactNode, useActionState, useEffect, useId, useRef, useState } from "react";
import { refused } from "./access";

/** A set being changed: its name, and what is in it, as grantr last said, read afresh. */
export interface Changing {
  readonly name: string;
  readonly chosen: readonly string[];
}

/** One choice of what a set may hold, and the group of choices it is shown in, if any. */
interface Choice {
  readonly value: string;
  readonly label: string;
  readonly group?: string;
}

/** How what is in a set is chosen: from choices, or typed, separated by commas, under a label. */
type Picking = { readonly choices: readonly Choice[] } | { readonly typed: string };

/** The form's words: its titles, its fields' labels, and its buttons'. */
interface Words {
  /** The new set's name field, such as "Group". */
  readonly name: string;
  /** What is in it, such as "Members". */
  readonly of: string;
  /** Creating one, such as "Create a group". */
  readonly create: string;
  /** Changing `name`'s, such as "Change ops's members". */
  readonly change: (name: string) => string;
  /** The buttons that create and save, such as "Create the group" and "Save the group". */
  readonly created: string;
  readonly saved: string;
}

export interface DefineSetProps {
  readonly words: Words;
  readonly changing: Changing | null;
  readonly picking: Picking;
  /** Why a new set's name can't be used, or null where it can. */
  readonly taken: (name: string) => Promise<string | null>;
  /** The set saved under `name`, holding `chosen`, and what to say; or why not. */
  readonly save: (name: string, chosen: readonly string[]) => Promise<Answer<string>>;
  /** What taking `removed`, never none, out of `name` loses: the confirmation's question and body. */
  readonly losing: (removed: readonly string[], name: string) => { title: string; body: string };
  /** A line beneath the title while a set is changed, such as what a change widens. */
  readonly note?: ReactNode;
  readonly onSaved: (said: string) => void;
  readonly onCancel: () => void;
}

/**
 * A set created, or one changed: grantr's one change to it, which replaces what it holds. A
 * change starts from what grantr holds, less anything no choice offers any more, which the
 * confirmation then names as taken out. Opening a change brings the form into view.
 */
export function DefineSet({
  words,
  changing,
  picking,
  taken,
  save,
  losing,
  note,
  onSaved,
  onCancel,
}: DefineSetProps) {
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const choices = "choices" in picking ? picking.choices : null;
  const offered = (key: string) => choices === null || choices.some((one) => one.value === key);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<readonly string[]>((changing?.chosen ?? []).filter(offered));
  const [typed, setTyped] = useState(chosen.join(", "));
  const keys = choices ? chosen : typed.split(/[\s,]+/).filter((key) => key !== "");
  const named = changing?.name ?? name.trim();
  const removed = (changing?.chosen ?? []).filter((key) => !keys.includes(key));

  useEffect(() => {
    if (changing) {
      heading.current?.focus();
      heading.current?.scrollIntoView({ block: "nearest" });
    }
  }, [changing]);

  async function saving(): Promise<Answer<string>> {
    const reason = changing === null ? await taken(named) : null;
    return reason === null ? save(named, keys) : refused(reason);
  }

  const [said, submit, pending] = useActionState(async (_last: string | null) => {
    const saved = await saving();
    if (saved.outcome === "refused") {
      return refusal("Not saved", saved);
    }
    onSaved(saved.result);
    return null;
  }, null);

  const lost = removed.length > 0 ? losing(removed, named) : null;
  return (
    <Card render={<section aria-labelledby={headingId} />} className="flex flex-col gap-3">
      <SectionTitle id={headingId} ref={heading} tabIndex={-1}>
        {changing ? words.change(changing.name) : words.create}
      </SectionTitle>
      {changing && note}
      <form className="flex flex-col gap-3" action={submit}>
        {changing === null && (
          <TextField
            label={words.name}
            name="name"
            autoComplete="off"
            required
            value={name}
            onValueChange={(value) => setName(String(value))}
          />
        )}
        {"choices" in picking ? (
          <Choices
            legend={words.of}
            choices={picking.choices}
            value={chosen}
            onValueChange={setChosen}
          />
        ) : (
          <TextField
            label={picking.typed}
            name="chosen"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onValueChange={(value) => setTyped(String(value))}
          />
        )}
        {said && <p role="alert">{said}</p>}
        <div className="flex flex-wrap gap-2">
          {lost ? (
            <ConfirmDialog
              label={words.saved}
              title={lost.title}
              confirm={words.saved}
              onConfirm={async () => onSaved(orThrow("Not saved", await saving()))}
            >
              <p>{lost.body}</p>
            </ConfirmDialog>
          ) : (
            <Button type="submit" disabled={pending}>
              {changing ? words.saved : words.created}
            </Button>
          )}
          {changing && (
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}

/** The choices: one checkbox group per group of them, or one under `legend`. */
function Choices({
  legend,
  choices,
  value,
  onValueChange,
}: {
  legend: string;
  choices: readonly Choice[];
  value: readonly string[];
  onValueChange: (value: readonly string[]) => void;
}) {
  const groups = [...new Set(choices.map((choice) => choice.group ?? legend))];
  return groups.map((group) => {
    const own = choices.filter((choice) => (choice.group ?? legend) === group);
    const isOwn = (key: string) => own.some((choice) => choice.value === key);
    return (
      <CheckboxGroup
        key={group}
        legend={group}
        choices={own}
        value={value.filter(isOwn)}
        onValueChange={(mine) => onValueChange([...value.filter((key) => !isOwn(key)), ...mine])}
      />
    );
  });
}
