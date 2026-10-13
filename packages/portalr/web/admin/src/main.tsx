import "@portalr/ui/styles.css";
import { AppShell, EmptyState, NavLink, PageHeader, SideNav } from "@portalr/ui";
import { House } from "lucide-react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

/**
 * admin's frame, with admin's own mark (lattice ADR-0014): its areas, and signing in, arrive with
 * portalr's phase 6, which decides the rest of the frame (portalr ADR-0021).
 */
const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html has no #root");
}
createRoot(root).render(
  <StrictMode>
    <AppShell
      ui="admin"
      home={<a href={import.meta.env.BASE_URL} />}
      switcher={null}
      account={null}
      nav={
        <SideNav label="Admin">
          <NavLink icon={House} href={import.meta.env.BASE_URL} aria-current="page">
            Home
          </NavLink>
        </SideNav>
      }
    >
      <PageHeader title="portalr admin" />
      <EmptyState title="Nothing to manage here yet">
        Access, the audit log, feedback, traces, and usage and spend arrive here, for a tenant's
        owners and admins and for the deployment's operators.
      </EmptyState>
    </AppShell>
  </StrictMode>,
);
