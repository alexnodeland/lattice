import { Menu } from "@base-ui/react/menu";
import { Check, ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import { Icon } from "./icon";
import { groupLabel, item, popup, separator } from "./menu";

/** A tenant or a workspace to choose, by its id, with a word about it. */
export type Choice = { readonly id: string; readonly detail?: string };

function Choices({
  label,
  choices,
  chosen,
  onChoose,
}: {
  label: string;
  choices: readonly Choice[];
  /** The id chosen now, if one is. */
  chosen?: string | undefined;
  onChoose: (id: string) => void;
}) {
  return (
    <Menu.Group>
      <Menu.GroupLabel className={groupLabel}>{label}</Menu.GroupLabel>
      <Menu.RadioGroup value={chosen ?? ""} onValueChange={(id: string) => onChoose(id)}>
        {choices.map(({ id, detail }) => (
          <Menu.RadioItem key={id} value={id} className={item}>
            <span className="data-checked:font-semibold">{id}</span>
            <span className="flex items-center gap-2 text-muted text-xs">
              {detail}
              <Menu.RadioItemIndicator className="text-accent">
                <Icon icon={Check} />
              </Menu.RadioItemIndicator>
            </span>
          </Menu.RadioItem>
        ))}
      </Menu.RadioGroup>
    </Menu.Group>
  );
}

/**
 * Where a person is: their tenant and workspace, or the tenant alone where they are choosing a
 * workspace, and a menu of the others to move to. Choosing hands the id to the caller, which
 * navigates.
 */
export function Switcher({
  tenant,
  workspace,
  tenants,
  workspaces,
  onTenant,
  onWorkspace,
  every,
}: {
  tenant: string;
  /** The workspace they are in; none on the tenant's list of workspaces. */
  workspace?: string;
  tenants: readonly Choice[];
  /** The workspaces in this tenant. */
  workspaces: readonly Choice[];
  onTenant: (id: string) => void;
  onWorkspace: (id: string) => void;
  /** A link to every workspace in the tenant, such as the router's, shown under them. */
  every?: ReactElement;
}) {
  const where = workspace === undefined ? null : { tenant, workspace };
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={where ? `Workspace: ${tenant}, ${where.workspace}` : `Tenant: ${tenant}`}
        className="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-edge bg-paper px-3 py-1.5 font-semibold text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus"
      >
        {where ? (
          <>
            <span aria-hidden="true" className="truncate font-medium text-muted">
              {where.tenant}
            </span>
            <span aria-hidden="true" className="font-normal text-muted">
              /
            </span>
            <span aria-hidden="true" className="truncate">
              {where.workspace}
            </span>
          </>
        ) : (
          <span aria-hidden="true" className="truncate">
            {tenant}
          </span>
        )}
        <Icon icon={ChevronDown} className="ml-auto text-muted" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="start" className="z-30">
          <Menu.Popup className={popup}>
            <Choices
              label={`Workspaces in ${tenant}`}
              choices={workspaces}
              chosen={workspace}
              onChoose={onWorkspace}
            />
            {every && <Menu.Separator className={separator} />}
            {every && (
              <Menu.LinkItem render={every} className={item}>
                Every workspace in {tenant}
              </Menu.LinkItem>
            )}
            <Menu.Separator className={separator} />
            <Choices label="Tenants" choices={tenants} chosen={tenant} onChoose={onTenant} />
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

/**
 * Where an admin is: a tenant, or every tenant, and a menu of the others. Choosing a tenant hands
 * its id to the caller; `everyTenant`, the link for operators, is offered only where given.
 */
export function TenantSwitcher({
  tenant,
  tenants,
  onTenant,
  everyTenant,
}: {
  /** The tenant chosen, or null for every tenant. */
  tenant: string | null;
  tenants: readonly Choice[];
  onTenant: (id: string) => void;
  /** A link to every tenant, such as the router's, for whoever may see them all. */
  everyTenant?: ReactElement;
}) {
  const named = tenant ?? "All tenants";
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={`Tenant: ${named}`}
        className="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-edge bg-paper px-3 py-1.5 font-semibold text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus"
      >
        <span aria-hidden="true" className="truncate">
          {named}
        </span>
        <Icon icon={ChevronDown} className="ml-auto text-muted" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="start" className="z-30">
          <Menu.Popup className={popup}>
            {tenants.length > 0 && (
              <Choices
                label="Tenants"
                choices={tenants}
                chosen={tenant ?? ""}
                onChoose={onTenant}
              />
            )}
            {everyTenant && tenants.length > 0 && <Menu.Separator className={separator} />}
            {everyTenant && (
              <Menu.LinkItem render={everyTenant} className={item}>
                All tenants
              </Menu.LinkItem>
            )}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
