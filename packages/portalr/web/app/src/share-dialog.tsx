/**
 * Sharing a thread: who holds a role on it, each with Revoke, and a role granted to a person, as
 * viewer or editor (portalr ADR-0022). grantr names people by id, so the dialog does too.
 */

import type { Answer, GrantrApi } from "@portalr/client";
import { Button, CommandButton, Dialog, TextField } from "@portalr/ui";
import { useActionState } from "react";

type Grant = GrantrApi.components["schemas"]["Grant"];
type Grantee = Grant["to"];

/** The roles a thread is shared with. */
const ROLES = ["viewer", "editor"] as const;

/** A grantee as the dialog names it: a person or a client by id, a group or a rule as such. */
function named(to: Grantee): string {
  switch (to.kind) {
    case "user":
    case "service_principal":
      return to.id;
    case "group":
      return `group ${to.id}`;
    case "rule":
      return `rule ${to.rule}`;
    default:
      return to satisfies never;
  }
}

export function ShareDialog({
  open,
  onOpenChange,
  grants,
  people,
  canRevoke,
  onGrant,
  onRevoke,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The grants on the thread. */
  grants: readonly Grant[];
  /** Who it may be shared with: people the tenant has, by id, not holding a role on it yet. */
  people: readonly string[];
  canRevoke: boolean;
  onGrant: (person: string, role: (typeof ROLES)[number]) => Promise<Answer<unknown>>;
  onRevoke: (grant: Grant) => Promise<Answer<unknown>>;
}) {
  const [refused, grant, granting] = useActionState(
    async (_last: string | null, form: FormData) => {
      const person = String(form.get("person"));
      const role = form.get("role") === "editor" ? "editor" : "viewer";
      const answer = await onGrant(person, role);
      return answer.outcome === "done" ? null : `Not shared: ${answer.reasons.join("; ")}`;
    },
    null,
  );
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Share the thread"
      description="Who holds a role on it. While it's restricted, they and the workspace's admins are the only ones who see it."
    >
      {grants.length === 0 ? (
        <p>No one holds a role on it yet.</p>
      ) : (
        <ul aria-label="People with access" className="flex flex-col gap-2">
          {grants.map((each) => (
            <li
              key={`${named(each.to)}:${each.role}`}
              aria-label={`${named(each.to)}, ${each.role}`}
              className="flex flex-wrap items-center justify-between gap-2"
            >
              <span>
                {named(each.to)} <span className="text-muted">{each.role}</span>
              </span>
              {canRevoke && <CommandButton onSend={() => onRevoke(each)}>Revoke</CommandButton>}
            </li>
          ))}
        </ul>
      )}
      {people.length > 0 && (
        <form aria-label="Share with someone" className="flex flex-col gap-2" action={grant}>
          <TextField
            label="Person"
            name="person"
            render={
              <select>
                {people.map((person) => (
                  <option key={person} value={person}>
                    {person}
                  </option>
                ))}
              </select>
            }
          />
          <TextField
            label="Role"
            name="role"
            error={refused}
            render={
              <select>
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            }
          />
          <Button type="submit" disabled={granting} className="self-start">
            Share
          </Button>
        </form>
      )}
    </Dialog>
  );
}
