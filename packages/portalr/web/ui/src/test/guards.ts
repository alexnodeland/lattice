/**
 * Every focus that lands on one of Base UI's focus guards while `run` goes: none, where a popup
 * keeps Tab in it at once (portalr ADR-0068).
 */
export async function guardsFocused(run: () => Promise<void>): Promise<Element[]> {
  const guarded: Element[] = [];
  const onGuard = (event: FocusEvent) => {
    if (event.target instanceof Element && event.target.hasAttribute("data-base-ui-focus-guard")) {
      guarded.push(event.target);
    }
  };
  document.addEventListener("focusin", onGuard);
  try {
    await run();
  } finally {
    document.removeEventListener("focusin", onGuard);
  }
  return guarded;
}
