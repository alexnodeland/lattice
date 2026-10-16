/**
 * Sharing a thread: who holds a role on it, each with Revoke, asked first (portalr ADR-0021), and a
 * role granted to a person, as viewer or editor (portalr ADR-0022). grantr names people by id, so the dialog does too.
 */

import { type Answer, type GrantrApi, refusal } from "@portalr/client";
import { Button, ConfirmDialog, Dialog, SelectField } from "@portalr/ui";
import { type RefObject, useActionState, useRef } from "react";

type Grant = GrantrApi.components["schemas"]["Grant"];
type Grantee = Grant["to"];
type AuditEntry = GrantrApi.components["schemas"]["AuditEntry"];

/** The roles a thread is shared with. */
const ROLES = ["viewer", "editor"] as const;
export type Role = (typeof ROLES)[number];

const isRole = (role: unknown): role is Role => ROLES.some((each) => each === role);

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
  finalFocus,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The grants on the thread, or null where the reader may not list them. */
  grants: readonly Grant[] | null;
  /** Who it may be shared with: people in the tenant, by id, not holding a role on it yet. */
  people: readonly string[];
  canRevoke: boolean;
  onGrant: (person: string, role: Role) => Promise<Answer<AuditEntry>>;
  onRevoke: (grant: Grant) => Promise<Answer<AuditEntry>>;
  /** Where focus goes when it closes: the menu it was opened from. */
  finalFocus?: RefObject<HTMLElement | null>;
}) {
  const person = useRef<HTMLButtonElement>(null);
  const [refused, grant, granting] = useActionState(
    async (_last: string | null, form: FormData) => {
      const role = form.get("role");
      if (!isRole(role)) {
        return `Not shared: ${String(role)} isn't a role a thread is shared with.`;
      }
      const answer = await onGrant(String(form.get("person")), role);
      return answer.outcome === "done" ? null : refusal("Not shared", answer);
    },
    null,
  );
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Share the thread"
      description="Who holds a role on it. While it's restricted, they, the workspace's admins and the tenant's owners and admins are the only ones who see it."
      {...(people.length > 0 && { initialFocus: person })}
      {...(finalFocus && { finalFocus })}
    >
      {grants === null ? (
        <p>You may share it, but not see who holds a role on it.</p>
      ) : grants.length === 0 ? (
        <p>No one holds a role on it yet.</p>
      ) : (
        <ul aria-label="People with access" className="flex flex-col gap-2">
          {grants.map((each) => (
            <li
              key={`${each.to.kind}:${named(each.to)}:${each.role}`}
              className="flex flex-wrap items-center justify-between gap-2"
            >
              <span>
                {named(each.to)} <span className="text-muted">{each.role}</span>
              </span>
              {canRevoke && (
                <ConfirmDialog
                  label="Revoke"
                  look="danger-soft"
                  size="sm"
                  title={`Revoke ${named(each.to)}'s ${each.role} role?`}
                  confirm="Revoke the role"
                  onConfirm={async () => {
                    const answer = await onRevoke(each);
                    if (answer.outcome !== "done") {
                      throw new Error(refusal("Not revoked", answer));
                    }
                  }}
                >
                  {named(each.to)} loses the {each.role} role on this thread. While it's restricted,
                  they no longer see it.
                </ConfirmDialog>
              )}
            </li>
          ))}
        </ul>
      )}
      {people.length === 0 ? (
        <p>
          There's no one else to share it with: everyone you can choose from holds a role on it
          already.
        </p>
      ) : (
        <form aria-label="Share with someone" className="flex flex-col gap-2" action={grant}>
          <SelectField
            triggerRef={person}
            label="Person"
            name="person"
            options={people.map((each) => ({ value: each, label: each }))}
          />
          <SelectField
            label="Role"
            name="role"
            options={ROLES.map((role) => ({ value: role, label: role }))}
          />
          {refused && <p role="alert">{refused}</p>}
          <Button type="submit" disabled={granting} className="self-start">
            Share
          </Button>
        </form>
      )}
    </Dialog>
  );
}
