/**
 * The deployment's brand kit, as `config.json` names it (lattice RFC-0007): who the product is,
 * its words, and its marks, each served under the kit's hash. None for portalr's own look. The
 * kit's look is already the page's, from its stylesheet; this is what the UIs draw and say.
 */

import type { Config } from "@portalr/client";
import { createContext, useContext } from "react";
import { cn } from "./cn";
import { UI_NAME, type Ui } from "./marks";

/** The kit `config.json` names. */
export type Brand = NonNullable<Config["brand"]>;

/** The deployment's kit, or null for portalr's own look; the UIs' roots provide it. */
export const BrandContext = createContext<Brand | null>(null);

/** The kit, where a deployment has one. */
export const useBrand = () => useContext(BrandContext);

/**
 * Where portalr is mounted: the kit's paths in `config.json` are relative to it. The UIs' builds
 * and their `config.json` are made for this mount (ui.py's `MOUNT`), so it is one place to change.
 */
const MOUNT = "/portalr/";

/** A path of the kit's, as `config.json` gives it, as the page fetches it. */
const brandUrl = (path: string) => `${MOUNT}${path}`;

/** The product's name in a UI: its own in the app, admin's in admin. */
export const brandName = (brand: Brand, ui: Ui) =>
  ui === "admin" ? brand.identity.admin : brand.identity.app;

/** A UI's name: the kit's where the deployment has one, else portalr's. */
const uiName = (brand: Brand | null | undefined, ui: Ui) =>
  brand ? brandName(brand, ui) : UI_NAME[ui];

/** A UI's name, as the page's kit says. */
export function useUiName(ui: Ui) {
  return uiName(useBrand(), ui);
}

/** A page's title: what it is, outermost last, then the UI's name. */
export const pageTitle = (brand: Brand | null | undefined, ui: Ui, ...parts: string[]) =>
  [...parts, uiName(brand, ui)].join(" · ");

/**
 * The kit's mark, in the scheme the page is in: the light file or the dark one, shown by
 * base.css as the page's scheme says, inside a box that takes the caller's classes, so a class
 * that hides the mark hides both. A picture of a name the link around it gives. Both files load,
 * as an image a page hides is still fetched: two small files, and a kit has both.
 */
export function BrandMark({ brand, className }: { brand: Brand; className?: string }) {
  return (
    <span className={cn("inline-flex shrink-0", className)}>
      <img
        alt=""
        src={brandUrl(brand.mark.light)}
        className="brand-light size-full object-contain"
      />
      <img alt="" src={brandUrl(brand.mark.dark)} className="brand-dark size-full object-contain" />
    </span>
  );
}
