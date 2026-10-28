import { Menu } from "@base-ui/react/menu";
import { type ReactNode, useId, useState } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { groupLabel, item, popup, separator } from "./menu";
import { SheetHandle, sheetPopup, sheetPositioner, useSheet } from "./sheet";
import { FEEDBACK, RING } from "./states";

/** The scheme a person chose: the system's, or one of the two. */
export type Appearance = "system" | "light" | "dark";

const APPEARANCES: readonly (readonly [Appearance, string])[] = [
  ["system", "System"],
  ["light", "Light"],
  ["dark", "Dark"],
];

/** An appearance as a segment of a three-way track (portalr ADR-0085), chosen on the surface. */
const SEGMENT = `flex-1 cursor-default rounded-(--segmented-item-radius) px-(--segmented-item-pad-x) py-(--segmented-item-pad-y) text-center font-medium text-muted outline-none data-checked:bg-surface data-checked:text-fg data-checked:shadow-(--card-shadow) data-highlighted:ring-(length:--focus-width) data-highlighted:ring-focus data-highlighted:ring-inset ${FEEDBACK}`;

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
  /** Whether a deletion the person's no asked for is still to be done, as the relay said. */
  readonly deleting?: boolean | undefined;
  /** Whether the person's last answer wasn't recorded: the switch shows the answer before it. */
  readonly failed?: boolean | undefined;
  /** The privacy guide, which says what is shared and how it is kept. */
  readonly guide: string;
  /** Session replay's switch, where the deployment records replays; it rests on this one's yes. */
  readonly replay?: ReplayAnswer | undefined;
}

/**
 * A person's answer to session replay (portalr ADR-0077), and the words its switch says, which
 * the app brings with it, so the first page's bytes hold none of them: no until the person turns
 * it on, which the relay takes only while they share how they use the app.
 */
export interface ReplayAnswer {
  readonly given: boolean;
  readonly onAnswer: (given: boolean) => void;
  /** Whether a deletion the person's no asked for is still to be done, as the relay said. */
  readonly deleting?: boolean | undefined;
  /** What is recorded, and how it is kept. */
  readonly guide: string;
  /** The switch's name, what it does, the link to the guide, and the note while a deletion is owed. */
  readonly words: { label: string; about: string; link: string; pending: string };
}

/** What the menu says while a deletion the person's no asked for isn't done yet. */
const STILL_DELETING =
  "Deleting what you shared hasn't finished yet. It will be retried until it is done.";

/** What a screen reader hears when an answer wasn't recorded. */
export const NOT_SAVED = "Your answer wasn't saved, so nothing has changed. Try again.";

/** What the account menu says, for a screen reader, as the person's answer changes. */
export function analyticsStatus(analytics: AnalyticsAnswer | undefined): string {
  if (!analytics) {
    return "";
  }
  const answer = analytics.given
    ? "Sharing how you use the app is on."
    : analytics.deleting
      ? `Sharing is off. ${STILL_DELETING}`
      : "Sharing how you use the app is off.";
  return analytics.failed ? `${NOT_SAVED} ${answer}` : answer;
}

const Note = ({ children }: { children: ReactNode }) => (
  <p className="px-2.5 pb-1.5 text-muted text-xs">{children}</p>
);

/** One of the Privacy group's switches: its words, the note while a deletion is owed, and a link. */
function PrivacySwitch({
  given,
  onAnswer,
  words,
  pending,
  guide,
  wrap = false,
}: {
  given: boolean;
  onAnswer: (given: boolean) => void;
  words: { label: string; about: string; link: string };
  pending: string | undefined;
  guide: string;
  /** Whether its description is held to a width, for a long one. */
  wrap?: boolean;
}) {
  const about = useId();
  return (
    <>
      <Menu.CheckboxItem
        checked={given}
        aria-describedby={about}
        onCheckedChange={(on) => onAnswer(on)}
        className={item}
      >
        <span className="flex flex-col">
          <span>{words.label}</span>
          <span
            aria-hidden="true"
            id={about}
            className={cn("font-normal text-muted text-xs", wrap && "max-w-72")}
          >
            {words.about}
          </span>
        </span>
        <Menu.CheckboxItemIndicator className="text-accent">
          <Icon icon={glyphs.check} />
        </Menu.CheckboxItemIndicator>
      </Menu.CheckboxItem>
      {pending && <Note>{pending}</Note>}
      <Menu.LinkItem href={guide} target="_blank" rel="noopener noreferrer" className={item}>
        {words.link}
        <span className="sr-only"> (opens in a new tab)</span>
        <Icon icon={glyphs.externalLink} className="shrink-0 text-muted" />
      </Menu.LinkItem>
    </>
  );
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
  const replay = analytics?.replay;
  // A deletion of recordings still owed, which is said whether or not the switch is on offer.
  const owed = replay !== undefined && !replay.given && replay.deleting === true;
  // Open or not, known here too, so the sheet's drag can close it on a phone (portalr ADR-0082).
  const [open, setOpen] = useState(false);
  const asSheet = useSheet(open, () => setOpen(false));
  return (
    <Menu.Root open={open} onOpenChange={setOpen}>
      <Menu.Trigger
        aria-label={`Account: ${name}`}
        className={cn(
          // Where its name is hidden, the bar's, the trigger is the avatar's circle, its wash too, in
          // both UIs alike (portalr ADR-0085); beside the name, the header's trigger shape.
          "inline-flex min-w-0 items-center gap-2 rounded-(--header-trigger-radius) p-1 pr-2 font-medium text-fg text-sm hover:bg-wash max-lg:rounded-full",
          RING,
          FEEDBACK,
        )}
      >
        <span
          aria-hidden="true"
          className="grid size-7 shrink-0 place-items-center rounded-full bg-line font-semibold text-fg text-xs"
        >
          {initials(name)}
        </span>
        <span aria-hidden="true" className="truncate max-lg:not-in-data-[drawer]:hidden">
          {name}
        </span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="end" className={`z-30 ${sheetPositioner}`}>
          <Menu.Popup ref={asSheet} className={`${popup} ${sheetPopup}`}>
            <SheetHandle />
            <Menu.Group>
              <Menu.GroupLabel className="px-2.5 pt-1.5 pb-1">
                <span className="block font-semibold">{name}</span>
                {email && <span className="block text-muted text-xs">{email}</span>}
              </Menu.GroupLabel>
              <Menu.Item className={item} onClick={onSignOut}>
                Sign out
                <Icon icon={glyphs.logOut} />
              </Menu.Item>
            </Menu.Group>
            <Menu.Separator className={separator} />
            <Menu.Group>
              <Menu.GroupLabel className={groupLabel}>Appearance</Menu.GroupLabel>
              <Menu.RadioGroup
                value={appearance}
                onValueChange={(chosen: Appearance) => onAppearance(chosen)}
                className="mx-4 mb-2 flex gap-0.5 rounded-(--segmented-radius) border border-line bg-subtle p-(--segmented-pad)"
              >
                {APPEARANCES.map(([value, label]) => (
                  <Menu.RadioItem key={value} value={value} className={SEGMENT}>
                    {label}
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
                  <Icon icon={glyphs.check} />
                </Menu.CheckboxItemIndicator>
              </Menu.CheckboxItem>
            </Menu.Group>
            {analytics && (
              <>
                <Menu.Separator className={separator} />
                <Menu.Group>
                  <Menu.GroupLabel className={groupLabel}>Privacy</Menu.GroupLabel>
                  <PrivacySwitch
                    given={analytics.given}
                    onAnswer={analytics.onAnswer}
                    words={{
                      label: "Share how I use the app",
                      about:
                        "Which pages you open, never what you write. Turning it off deletes what you shared.",
                      link: "How sharing works",
                    }}
                    pending={!analytics.given && analytics.deleting ? STILL_DELETING : undefined}
                    guide={analytics.guide}
                  />
                  {replay && (analytics.given || owed) && (
                    <>
                      <Menu.Separator className={separator} />
                      {analytics.given ? (
                        <PrivacySwitch
                          given={replay.given}
                          onAnswer={replay.onAnswer}
                          words={replay.words}
                          pending={owed ? replay.words.pending : undefined}
                          guide={replay.guide}
                          wrap
                        />
                      ) : (
                        <Note>{replay.words.pending}</Note>
                      )}
                    </>
                  )}
                </Menu.Group>
              </>
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
