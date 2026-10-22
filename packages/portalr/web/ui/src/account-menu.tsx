import { Menu } from "@base-ui/react/menu";
import { Check, LogOut } from "lucide-react";
import { useId } from "react";
import { Icon } from "./icon";
import { groupLabel, item, popup, separator } from "./menu";

/** The scheme a person chose: the system's, or one of the two. */
export type Appearance = "system" | "light" | "dark";

const APPEARANCES: readonly (readonly [Appearance, string])[] = [
  ["system", "Follow the system"],
  ["light", "Light"],
  ["dark", "Dark"],
];

/** Two letters for a name: its first and last words' initials. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  return `${words[0]?.[0] ?? ""}${words.length > 1 ? (words.at(-1)?.[0] ?? "") : ""}`.toUpperCase();
}

/**
 * A person's answer to product analytics, where the deployment has it (lattice RFC-0008): no until
 * they turn it on, and theirs to turn off, which deletes what they shared.
 */
export interface AnalyticsAnswer {
  readonly given: boolean;
  readonly onAnswer: (given: boolean) => void;
}

/**
 * Who is signed in, signing out, their scheme, colour-blind friendly charts, and, where the
 * deployment has product analytics, whether they share how they use the app.
 */
export function AccountMenu({
  name,
  email,
  appearance,
  onAppearance,
  colourBlind,
  onColourBlind,
  analytics,
  onSignOut,
}: {
  name: string;
  email?: string;
  appearance: Appearance;
  onAppearance: (appearance: Appearance) => void;
  /** Whether colour-blind friendly charts are on: a palette and patterns that hold for every reader. */
  colourBlind: boolean;
  onColourBlind: (on: boolean) => void;
  /** The person's answer to product analytics, or none where the deployment hasn't it. */
  analytics?: AnalyticsAnswer | undefined;
  onSignOut: () => void;
}) {
  const hint = useId();
  const sharing = useId();
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={`Account: ${name}`}
        className="inline-flex min-w-0 items-center gap-2 rounded-(--header-trigger-radius) p-1 pr-2 font-medium text-fg text-sm outline-offset-(--focus-offset) hover:bg-wash focus-visible:outline-(length:--focus-width) focus-visible:outline-focus"
      >
        <span
          aria-hidden="true"
          className="grid size-7 shrink-0 place-items-center rounded-full bg-wash font-semibold text-accent text-xs"
        >
          {initials(name)}
        </span>
        <span aria-hidden="true" className="truncate max-lg:not-in-data-[drawer]:hidden">
          {name}
        </span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="end" className="z-30">
          <Menu.Popup className={popup}>
            <Menu.Group>
              <Menu.GroupLabel className="px-2.5 pt-1.5 pb-1">
                <span className="block font-semibold">{name}</span>
                {email && <span className="block text-muted text-xs">{email}</span>}
              </Menu.GroupLabel>
              <Menu.Item className={item} onClick={onSignOut}>
                Sign out
                <Icon icon={LogOut} />
              </Menu.Item>
            </Menu.Group>
            <Menu.Separator className={separator} />
            <Menu.Group>
              <Menu.GroupLabel className={groupLabel}>Appearance</Menu.GroupLabel>
              <Menu.RadioGroup
                value={appearance}
                onValueChange={(chosen: Appearance) => onAppearance(chosen)}
              >
                {APPEARANCES.map(([value, label]) => (
                  <Menu.RadioItem key={value} value={value} className={item}>
                    {label}
                    <Menu.RadioItemIndicator className="text-accent">
                      <Icon icon={Check} />
                    </Menu.RadioItemIndicator>
                  </Menu.RadioItem>
                ))}
              </Menu.RadioGroup>
            </Menu.Group>
            <Menu.Separator className={separator} />
            <Menu.Group>
              <Menu.GroupLabel className={groupLabel}>Colour</Menu.GroupLabel>
              <Menu.CheckboxItem
                checked={colourBlind}
                aria-describedby={hint}
                onCheckedChange={(on) => onColourBlind(on)}
                className={item}
              >
                <span className="flex flex-col">
                  <span>Colour-blind friendly charts</span>
                  <span aria-hidden="true" id={hint} className="font-normal text-muted text-xs">
                    Changes chart colours and adds patterns
                  </span>
                </span>
                <Menu.CheckboxItemIndicator className="text-accent">
                  <Icon icon={Check} />
                </Menu.CheckboxItemIndicator>
              </Menu.CheckboxItem>
            </Menu.Group>
            {analytics && (
              <>
                <Menu.Separator className={separator} />
                <Menu.Group>
                  <Menu.GroupLabel className={groupLabel}>Privacy</Menu.GroupLabel>
                  <Menu.CheckboxItem
                    checked={analytics.given}
                    aria-describedby={sharing}
                    onCheckedChange={(on) => analytics.onAnswer(on)}
                    className={item}
                  >
                    <span className="flex flex-col">
                      <span>Share how I use the app</span>
                      <span
                        aria-hidden="true"
                        id={sharing}
                        className="font-normal text-muted text-xs"
                      >
                        Which pages and features you open, never what you write. Off deletes it.
                      </span>
                    </span>
                    <Menu.CheckboxItemIndicator className="text-accent">
                      <Icon icon={Check} />
                    </Menu.CheckboxItemIndicator>
                  </Menu.CheckboxItem>
                </Menu.Group>
              </>
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
