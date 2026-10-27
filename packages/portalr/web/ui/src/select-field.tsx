import { Select } from "@base-ui/react/select";
import { type ReactNode, type Ref, useMemo, useState } from "react";
import { cn } from "./cn";
import { FormField } from "./form-field";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { item, popover } from "./menu";
import { FEEDBACK, RING } from "./states";

/** One of a select's choices: the value it gives, and the words it shows as. */
export interface Option {
  readonly value: string;
  readonly label: string;
}

/**
 * A labelled choice among several, Base UI's Select on the kit's own surface: the trigger has a
 * control's edge and height and a chevron, and the choices float as a menu's do. It is named by its
 * label, and keeps the platform's select's keyboard: arrow keys move through the choices, typing
 * finds one by its first letters, Enter chooses it, Escape closes the list and gives the focus
 * back. With a `name` it submits with its form, as a native select does. Uncontrolled, it starts
 * on `defaultValue` or its first choice, as a native select does, and follows its first choice as
 * the choices change until one is chosen.
 */
export function SelectField({
  label,
  hint,
  error = null,
  options,
  value,
  defaultValue,
  onValueChange,
  name,
  required,
  disabled,
  className,
  triggerRef,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  /** The choices, each a value and the words it shows as. */
  options: readonly Option[];
  /** The value chosen, where the caller keeps it; with `onValueChange`. */
  value?: string;
  /** The value chosen to begin with, where the select keeps it. */
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  name?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  /** The trigger, for focus to be put on it. */
  triggerRef?: Ref<HTMLButtonElement>;
}) {
  const items = useMemo(() => [...options], [options]);
  // Until one is chosen, an uncontrolled select is on `defaultValue`, or on whatever its first choice
  // is now: the choices may arrive after it is shown, as the people a thread is shared with do.
  const [chosen, setChosen] = useState<string | null>(null);
  const shown = value ?? chosen ?? defaultValue ?? options[0]?.value ?? "";
  return (
    <FormField label={label} hint={hint} error={error} className={className}>
      <Select.Root
        items={items}
        // The pointer resting on a choice doesn't take the highlight or the focus, as on the
        // platform's select: the keys keep them, and Tab leaves a list the pointer is over.
        highlightItemOnHover={false}
        value={shown}
        onValueChange={(next) => {
          const picked = String(next ?? "");
          setChosen(picked);
          onValueChange?.(picked);
        }}
        {...(name !== undefined && { name })}
        {...(required !== undefined && { required })}
        {...(disabled !== undefined && { disabled })}
      >
        <Select.Trigger
          ref={triggerRef}
          className={cn(
            "inline-flex w-full items-center justify-between gap-2 rounded-(--input-radius) border border-edge bg-surface px-(--input-pad-x) py-(--input-pad-y) text-fg text-sm hover:not-data-disabled:bg-wash data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-line data-disabled:text-muted",
            RING,
            FEEDBACK,
          )}
        >
          <Select.Value className="truncate" />
          <Select.Icon className="text-muted">
            <Icon icon={glyphs.chevronDown} />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Positioner sideOffset={4} alignItemWithTrigger={false} className="z-50">
            <Select.Popup
              className={`${popover} max-h-[min(18rem,var(--available-height))] min-w-(--anchor-width) overflow-y-auto p-1.5 outline-none`}
            >
              <Select.List>
                {options.map((option) => (
                  <Select.Item
                    key={option.value}
                    value={option.value}
                    // The pointer shows where it rests, as the keys' highlight doesn't follow it.
                    className={`${item} hover:bg-wash data-selected:font-semibold`}
                  >
                    <Select.ItemText>{option.label}</Select.ItemText>
                    <Select.ItemIndicator className="text-accent">
                      <Icon icon={glyphs.check} />
                    </Select.ItemIndicator>
                  </Select.Item>
                ))}
              </Select.List>
            </Select.Popup>
          </Select.Positioner>
        </Select.Portal>
      </Select.Root>
    </FormField>
  );
}
