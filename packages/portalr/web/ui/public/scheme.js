// What a person chose for this browser, which the app's appearance.ts and colour-blind.ts keep: the
// scheme, and colour-blind mode, set before the first paint so a dark choice never flashes light
// and the charts never flash their usual palette. A file, not an inline script, as the UIs' CSP
// allows 'self'.
(() => {
  try {
    const chosen = localStorage.getItem("portalr-appearance");
    if (chosen === "light" || chosen === "dark") {
      document.documentElement.dataset.theme = chosen;
    }
    if (localStorage.getItem("portalr-colour-blind") === "on") {
      document.documentElement.dataset.cvd = "";
    }
  } catch {
    // Without storage, the system's scheme stands, and the mode is off.
  }
})();
