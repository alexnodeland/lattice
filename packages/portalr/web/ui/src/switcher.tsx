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
  chosen: string;
  onChoose: (id: string) => void;
}) {
  return (
    <Menu.Group>
      <Menu.GroupLabel className={groupLabel}>{label}</Menu.GroupLabel>
      <Menu.RadioGroup value={chosen} onValueChange={(id: string) => onChoose(id)}>
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
 * Where a person is: their tenant and workspace, and a menu of the others to move to. Choosing
 * hands the id to the caller, which navigates.
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
  workspace: string;
  tenants: readonly Choice[];
  /** The workspaces in this tenant. */
  workspaces: readonly Choice[];
  onTenant: (id: string) => void;
  onWorkspace: (id: string) => void;
  /** A link to every workspace in the tenant, such as the router's, shown under them. */
  every?: ReactElement;
}) {
  return (
    <Menu.Root>
      <Menu.Trigger
        aria-label={`Workspace: ${tenant}, ${workspace}`}
        className="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-edge bg-paper px-3 py-1.5 font-semibold text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus"
      >
        <span aria-hidden="true" className="truncate font-medium text-muted">
          {tenant}
        </span>
        <span aria-hidden="true" className="font-normal text-muted">
          /
        </span>
        <span aria-hidden="true" className="truncate">
          {workspace}
        </span>
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
