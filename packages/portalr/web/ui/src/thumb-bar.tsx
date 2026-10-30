/**
 * The thumb bar (portalr ADR-0082): on a phone, the active request's next step, Next or Answer
 * on a question, Approve on a plain approval, within the thumb's reach in the composer's row, so
 * a question far up the thread is answered without scrolling back to it. The bar's button presses
 * the request's own, marked `data-thumb-action` by its card, so the handlers are the card's; it
 * is hidden from assistive technology, which reaches the one in the card, so there is one tab
 * stop. Its words and its disabled state follow that button's. It gives way while the card's own
 * button is in view, not off the window, scrolled out of the tray it sits in or under the dock,
 * while the on-screen keyboard is up, and in a short window.
 */

import { useEffect, useState } from "react";
import { Button } from "./button";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { usePhone } from "./touch";

/** The card's button the bar mirrors, if it is one to mirror. */
const ACTION = "[data-thumb-action]";

/** What the bar shows: the words and whether the action can be taken, or nothing. */
type Mirror = { word: string; disabled: boolean } | null;

export function ThumbBar({ target }: { target: string }) {
  const phone = usePhone();
  const [mirror, setMirror] = useState<Mirror>(null);
  useEffect(() => {
    if (!phone) {
      return;
    }
    const card = document.getElementById(target);
    if (card === null) {
      return;
    }
    const root = document.documentElement;
    let frame = 0;
    // Read once a frame, however many scrolls, mutations and resizes asked.
    const read = () => {
      frame = 0;
      const action = card.querySelector<HTMLButtonElement>(ACTION);
      if (action === null) {
        setMirror(null);
        return;
      }
      const box = action.getBoundingClientRect();
      // Seen where what is at its centre is the button: not off the window, nor scrolled out of the
      // tray it may sit in, nor under the dock.
      const seen = action.contains(
        document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2),
      );
      // The keyboard's inset is kept on the root (`keyboardInset`): up, the bar would crowd it.
      const keyboard = Number.parseFloat(root.style.getPropertyValue("--keyboard-inset")) > 0;
      setMirror(
        seen || keyboard
          ? null
          : { word: action.textContent?.trim() ?? "", disabled: action.disabled },
      );
    };
    const soon = () => {
      frame ||= requestAnimationFrame(read);
    };
    read();
    const heard = new MutationObserver(soon);
    heard.observe(card, { subtree: true, childList: true, characterData: true, attributes: true });
    // The root's style also changes as the tray shows or hides (its `hidden`): the dock's
    // ResizeObserver writes `--composer-clearance` there, and that is what reads the bar again.
    const keyboarded = new MutationObserver(soon);
    keyboarded.observe(root, { attributes: true, attributeFilter: ["style"] });
    // Scrolls anywhere, as the card may sit in a box that scrolls on its own.
    document.addEventListener("scroll", soon, { capture: true, passive: true });
    window.addEventListener("resize", soon);
    return () => {
      heard.disconnect();
      keyboarded.disconnect();
      document.removeEventListener("scroll", soon, { capture: true });
      window.removeEventListener("resize", soon);
      cancelAnimationFrame(frame);
    };
  }, [phone, target]);
  if (!phone || mirror === null || mirror.word === "") {
    return null;
  }
  return (
    <span data-thumb-bar="" aria-hidden="true" className="ml-auto short:hidden">
      <Button
        tabIndex={-1}
        disabled={mirror.disabled}
        onClick={() => {
          const card = document.getElementById(target);
          card?.querySelector<HTMLButtonElement>(ACTION)?.click();
          card?.scrollIntoView({ block: "nearest" });
        }}
      >
        {mirror.word}
        <Icon icon={glyphs.arrowRight} className="size-3.5" />
      </Button>
    </span>
  );
}
