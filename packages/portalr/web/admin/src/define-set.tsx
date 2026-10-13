/**
 * The form grantr's named sets share: a group's members and a custom role's actions. Each is
 * created under a name not yet taken, or changed from its row, starting from what grantr last
 * said; grantr replaces it whole, and a change that takes anything out is confirmed first, saying
 * what is lost (portalr ADR-0024, ADR-0025).
 */

import { type Answer, orThrow, type Refusal, refusal } from "@portalr/client";
import {
  Button,
  Card,
  type CheckboxChoice,
  CheckboxGroup,
  ConfirmDialog,
  SectionTitle,
  TextField,
} from "@portalr/ui";
import { useActionState, useId, useState } from "react";

/** A set being changed: its name, and what is in it, as grantr last said, read afresh. */
export interface Changing {
  readonly name: string;
  readonly chosen: readonly string[];
}

/** A refusal of the form's own, before grantr is asked: no status, and why. */
export const refused = (reason: string): Refusal => ({
  outcome: "refused",
  status: 0,
  reasons: [reason],
});

/** "1 member", "2 members". */
export const counted = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

const capital = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);

/** A set created, or one changed: grantr's one change to it, which replaces what it holds. */
export function DefineSet({
  noun,
  of,
  changing,
  choices,
  typed: typedLabel = "",
  taken,
  save,
  losing,
  onSaved,
  onCancel,
}: {
  /** What the set is, such as "group". */
  noun: string;
  /** What is in it, such as "members", its choices' legend. */
  of: string;
  changing: Changing | null;
  /** The choices to check, or null where they're typed, separated by commas. */
  choices: readonly CheckboxChoice[] | null;
  /** The typed field's label, where there are no choices. */
  typed?: string;
  /** Why a new set's name can't be used, or null where it can. */
  taken: (name: string) => Promise<string | null>;
  /** The set saved under `name`, holding `chosen`, and what to say; or why not. */
  save: (name: string, chosen: readonly string[]) => Promise<Answer<string>>;
  /** What taking `removed` out of `name` loses, for the confirmation's question and body. */
  losing: (removed: readonly string[], name: string) => { title: string; body: string };
  onSaved: (said: string) => void;
  onCancel: () => void;
}) {
  const heading = useId();
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<readonly string[]>(changing?.chosen ?? []);
  const [typed, setTyped] = useState(chosen.join(", "));
  const keys = choices ? chosen : typed.split(/[\s,]+/).filter((key) => key !== "");
  const named = changing?.name ?? name.trim();
  const removed = (changing?.chosen ?? []).filter((key) => !keys.includes(key));
  const lost = losing(removed, named);

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

  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>
        {changing ? `Change ${changing.name}'s ${of}` : `Create a ${noun}`}
      </SectionTitle>
      <form className="flex flex-col gap-3" action={submit}>
        {changing === null && (
          <TextField
            label={capital(noun)}
            name={noun}
            autoComplete="off"
            required
            value={name}
            onValueChange={(value) => setName(String(value))}
          />
        )}
        {choices ? (
          <CheckboxGroup
            legend={capital(of)}
            choices={choices}
            value={chosen}
            onValueChange={setChosen}
          />
        ) : (
          <TextField
            label={typedLabel}
            name={of}
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onValueChange={(value) => setTyped(String(value))}
          />
        )}
        {said && <p role="alert">{said}</p>}
        <div className="flex flex-wrap gap-2">
          {removed.length > 0 ? (
            <ConfirmDialog
              label={`Save the ${noun}`}
              title={lost.title}
              confirm={`Save the ${noun}`}
              onConfirm={async () => onSaved(orThrow("Not saved", await saving()))}
            >
              <p>{lost.body}</p>
            </ConfirmDialog>
          ) : (
            <Button type="submit" disabled={pending}>
              {changing ? `Save the ${noun}` : `Create the ${noun}`}
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
