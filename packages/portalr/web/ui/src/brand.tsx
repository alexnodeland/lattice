/**
 * The deployment's brand kit, as `config.json` names it (lattice RFC-0007): who the product is,
 * its words, and its marks, each served under the kit's hash. None for portalr's own look. The
 * kit's look is already the page's, from its stylesheet; this is what the UIs draw and say.
 */

import type { Config } from "@portalr/client";
import { createContext, useContext } from "react";
import { cn } from "./cn";
import type { Ui } from "./marks";

/** The kit `config.json` names. */
export type Brand = NonNullable<Config["brand"]>;

/** The deployment's kit, or null for portalr's own look; the UIs' roots provide it. */
export const BrandContext = createContext<Brand | null>(null);

/** The kit, where a deployment has one. */
export const useBrand = () => useContext(BrandContext);

/** Where portalr is mounted: the kit's paths in `config.json` are relative to it. */
const MOUNT = "/portalr/";

/** A path of the kit's, as `config.json` gives it, as the page fetches it. */
export const brandUrl = (path: string) => `${MOUNT}${path}`;

/** The product's name in a UI: its own in the app, admin's in admin. */
export const brandName = (brand: Brand, ui: Ui) =>
  ui === "admin" ? brand.identity.admin : brand.identity.app;

/**
 * The kit's mark, in the scheme the page is in: the light file or the dark one, shown by
 * base.css as the page's scheme says. A picture of a name the link around it gives.
 */
export function BrandMark({ brand, className }: { brand: Brand; className?: string }) {
  return (
    <>
      <img alt="" src={brandUrl(brand.mark.light)} className={cn("brand-light", className)} />
      <img alt="" src={brandUrl(brand.mark.dark)} className={cn("brand-dark", className)} />
    </>
  );
}
