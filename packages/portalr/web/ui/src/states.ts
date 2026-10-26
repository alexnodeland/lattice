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
