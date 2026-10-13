import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import type { ReactNode } from "react";
import { Button } from "./button";
import { actions, backdrop, description as described, popup, title as titled } from "./dialog";

/**
 * A dialog over the page, opened by its caller: its title, what it's about, what it holds, and a
 * way to close it. Focus stays in it while it's open, and returns where it was when it closes.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  close = "Close",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  /** The words on the button that closes it. */
  close?: string;
  children: ReactNode;
}) {
  return (
    <BaseDialog.Root open={open} onOpenChange={onOpenChange}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className={backdrop} />
        <BaseDialog.Popup className={popup}>
          <BaseDialog.Title className={titled}>{title}</BaseDialog.Title>
          {description && (
            <BaseDialog.Description className={described}>{description}</BaseDialog.Description>
          )}
          {children}
          <div className={actions}>
            <BaseDialog.Close render={<Button variant="secondary" />}>{close}</BaseDialog.Close>
          </div>
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}
