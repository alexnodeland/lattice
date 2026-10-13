// The scheme a person chose, which the app's appearance.ts keeps, set before the first paint so a
// dark choice never flashes light. A file, not an inline script, as the UIs' CSP allows 'self'.
(() => {
  try {
    const chosen = localStorage.getItem("portalr-appearance");
    if (chosen === "light" || chosen === "dark") {
      document.documentElement.dataset.theme = chosen;
    }
  } catch {
    // Without storage, the system's scheme stands.
  }
})();
