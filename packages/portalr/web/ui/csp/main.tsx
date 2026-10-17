/**
 * The page the CSP tests drive: ui's Markdown, built as app and admin are, and served with portalr's
 * Content-Security-Policy (`policy.txt`), so whatever it renders meets the policy the UIs meet.
 */

import "../src/styles.css";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { type Addons, AddonsProvider, Markdown } from "../src";

declare global {
  interface Window {
    /** Render Markdown, as a message or as one streaming, with the add-ons a workspace allows. */
    show: (text: string, options?: { streaming?: boolean; addons?: Addons }) => void;
    /** Stream Markdown in, a character at a time, as an agent's run does. */
    stream: (text: string) => void;
  }
}

const root = createRoot(document.getElementById("root") as HTMLElement);

window.show = (text, { streaming = false, addons = { mermaid: false } } = {}) => {
  flushSync(() =>
    root.render(
      <AddonsProvider value={addons}>
        <Markdown streaming={streaming}>{text}</Markdown>
      </AddonsProvider>,
    ),
  );
};

window.stream = (text) => {
  for (let end = 1; end <= text.length; end += 1) {
    window.show(text.slice(0, end), { streaming: true });
  }
  window.show(text);
};
