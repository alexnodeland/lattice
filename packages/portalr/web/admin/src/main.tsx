import { Page } from "@portalr/ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html has no #root");
}
createRoot(root).render(
  <StrictMode>
    <Page title="portalr admin" />
  </StrictMode>,
);
