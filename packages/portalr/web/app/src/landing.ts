/** Where a signed-in person lands, from the tenants grantr says they are a member of. */

/** A person in no tenant has no access; one in a single tenant goes straight to it. */
export type Landing =
  | { readonly kind: "no-access" }
  | { readonly kind: "tenant"; readonly tenant: string }
  | { readonly kind: "choose"; readonly tenants: readonly string[] };

export function landing(memberships: readonly { readonly tenant: string }[]): Landing {
  const tenants = [...new Set(memberships.map((membership) => membership.tenant))].sort();
  const [only] = tenants;
  if (only === undefined) {
    return { kind: "no-access" };
  }
  return tenants.length === 1 ? { kind: "tenant", tenant: only } : { kind: "choose", tenants };
}
