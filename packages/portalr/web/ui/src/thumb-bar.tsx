/**
 * The thumb bar (portalr ADR-0082): on a phone, the active request's primary action, Answer or
 * Approve, within the thumb's reach above the composer, so a question far up the thread is
 * answered without scrolling back to it. The bar's button presses the request's own submit
 * button, so the handlers are the request's; it is hidden from assistive technology, which
 * reaches the one in the request, so there is one tab stop. Its words follow that button's. In a
 * short window it gives way, so what is pinned never covers most of the page.
 */

import { useEffect, useState } from "react";
import { Button } from "./button";
import { usePhone } from "./sheet";

export function ThumbBar({ target }: { target: string }) {
  const phone = usePhone();
  const [word, setWord] = useState("");
  useEffect(() => {
    if (!phone) {
      return;
    }
    const form = document.getElementById(target);
    if (form === null) {
      return;
    }
    const read = () =>
      setWord(
        form.querySelector<HTMLButtonElement>("button[type=submit]")?.textContent?.trim() ?? "",
      );
    read();
    const heard = new MutationObserver(read);
    heard.observe(form, { subtree: true, childList: true, characterData: true });
    return () => heard.disconnect();
  }, [phone, target]);
  if (!phone || word === "") {
    return null;
  }
  return (
    <div data-thumb-bar="" aria-hidden="true" className="flex justify-end pb-2 short:hidden">
      <Button
        tabIndex={-1}
        onClick={() => {
          const form = document.getElementById(target);
          form?.querySelector<HTMLButtonElement>("button[type=submit]")?.click();
          form?.scrollIntoView({ block: "nearest" });
        }}
      >
        {word}
      </Button>
    </div>
  );
}
