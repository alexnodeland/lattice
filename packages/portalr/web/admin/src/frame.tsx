/**
 * admin's frame: ui's AppShell with admin's mark, its own tenant switch, the areas of where the
 * admin is, and the account. A tenant's owners and admins switch between their tenants; an
 * operator also to every tenant, where only the deployment's areas show (portalr ADR-0021).
 */

import type { Signed } from "@portalr/client";
import { Account, AppShell, TenantSwitcher } from "@portalr/ui";
import { Link, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

export function Frame({
  tenant,
  tenants,
  operator,
  signed,
  nav,
  children,
}: {
  /** The tenant chosen, or null for every tenant. */
  tenant: string | null;
  /** The tenants the admin owns or administers. */
  tenants: readonly string[];
  operator: boolean;
  signed: Signed;
  nav: ReactNode;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <AppShell
      ui="admin"
      home={<Link to="/" />}
      switcher={
        <TenantSwitcher
          tenant={tenant}
          tenants={tenants.map((id) => ({ id }))}
          onTenant={(id) => void navigate({ to: "/t/$tenant", params: { tenant: id } })}
          {...(operator && { everyTenant: <Link to="/deployment" /> })}
        />
      }
      nav={nav}
      account={<Account signed={signed} />}
    >
      {children}
    </AppShell>
  );
}
