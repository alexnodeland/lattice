/**
 * A thread's menu: restricting it to the people it's shared with, or lifting that, and sharing
 * it, each where grantr allows (portalr ADR-0022).
 */

import { Menu } from "@base-ui/react/menu";
import type { Answer } from "@portalr/client";
import { Button, menu } from "@portalr/ui";
import { useState } from "react";

export function ThreadMenu({
  restricted,
  canRestrict,
  canShare,
  onRestrict,
  onShare,
}: {
  /** Whether only the people it's shared with, and the workspace's admins, see it. */
  restricted: boolean;
  canRestrict: boolean;
  canShare: boolean;
  /** Restrict it, or lift its restriction: the opposite of `restricted`. */
  onRestrict: () => Promise<Answer<unknown>>;
  onShare: () => void;
}) {
  const [refused, setRefused] = useState<string | null>(null);
  if (!(canRestrict || canShare)) {
    return null;
  }
  async function restrict() {
    const answer = await onRestrict();
    setRefused(answer.outcome === "done" ? null : answer.reasons.join("; "));
  }
  return (
    <span className="inline-flex flex-col gap-1">
      <Menu.Root>
        <Menu.Trigger render={<Button variant="secondary" />}>Thread actions</Menu.Trigger>
        <Menu.Portal>
          <Menu.Positioner sideOffset={4} align="end" className="z-30">
            <Menu.Popup className={menu.popup}>
              {canShare && (
                <Menu.Item className={menu.item} onClick={onShare}>
                  Share…
                </Menu.Item>
              )}
              {canRestrict && (
                <Menu.Item className={menu.item} onClick={() => void restrict()}>
                  {restricted ? "Lift restriction" : "Restrict"}
                </Menu.Item>
              )}
            </Menu.Popup>
          </Menu.Positioner>
        </Menu.Portal>
      </Menu.Root>
      {refused && <p role="alert">That wasn't done: {refused}</p>}
    </span>
  );
}
