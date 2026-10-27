/**
 * What every control shares (portalr ADR-0079): the kit's focus ring, drawn outside a control the
 * keyboard reaches, and its feedback, how its colours follow the pointer and the keyboard when it
 * is hovered, pressed or chosen, in `--feedback-duration`, and at once where motion is reduced. A
 * button's feedback is on tokens of its own (ADR-0037); everything else takes these.
 */

export const RING =
  "outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus";

export const FEEDBACK =
  "transition-[color,background-color,border-color,text-decoration-color] duration-(--feedback-duration) ease-(--feedback-ease) motion-reduce:transition-none";

/**
 * What waits on the reader carries a tick inside its surface (portalr ADR-0081): a short rule in
 * the working colour at the card's edge, at the height of its head line, on an asking card and
 * an approval; no margin column, no rule down the side.
 */
export const ASKING =
  "relative before:absolute before:top-(--question-pad) before:left-0 before:h-5 before:w-0.5 before:rounded-e-full before:bg-accent before:content-['']";
