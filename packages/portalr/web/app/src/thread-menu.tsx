/**
 * A thread's menu: sharing it, and restricting it to the people it's shared with or lifting
 * that, each where grantr allows (portalr ADR-0022).
 */

import { type Answer, type GrantrApi, refusal } from "@portalr/client";
import { Menu, type MenuItem } from "@portalr/ui";
import { type Ref, startTransition, useActionState } from "react";

type AuditEntry = GrantrApi.components["schemas"]["AuditEntry"];

export function ThreadMenu({
  restricted,
  onRestrict,
  onShare,
  triggerRef,
}: {
  /** Whether it's restricted, or null for no Restrict item: whoever may not read that. */
  restricted: boolean | null;
  /** Restrict it, or lift its restriction: the opposite of `restricted`. */
  onRestrict: () => Promise<Answer<AuditEntry>>;
  /** Open its sharing, or null for no Share item. */
  onShare: (() => void) | null;
  /** The menu's button, which focus returns to from its sharing. */
  triggerRef?: Ref<HTMLButtonElement>;
}) {
  const [refused, restrict, restricting] = useActionState(async () => {
    const answer = await onRestrict();
    return answer.outcome === "done" ? null : refusal("That wasn't done", answer);
  }, null);
  const items: MenuItem[] = [
    ...(onShare ? [{ label: "Share…", onSelect: onShare }] : []),
    ...(restricted === null
      ? []
      : [
          {
            label: restricted ? "Lift restriction" : "Restrict",
            onSelect: () => startTransition(restrict),
            disabled: restricting,
          },
        ]),
  ];
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col items-end gap-1">
      <Menu label="Thread actions" items={items} {...(triggerRef && { triggerRef })} />
      {refused && <p role="alert">{refused}</p>}
    </div>
  );
}
