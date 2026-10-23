/**
 * What a UI's build holds, read from the bundle as Rollup and Rolldown write it, apart from Vite,
 * so a test reads it too: `bundle-checks` fails the build on it.
 */

/** An add-on's module, ui's or a UI's own (portalr ADR-0044). */
const ADDON = /[\\/]src[\\/]on-demand[\\/][a-z][a-z-]*\.tsx?$/;

/** What `loadedWithout` reads of a bundle: its chunks, as Rollup and Rolldown write them. */
export type Bundled = Readonly<
  Record<
    string,
    | {
        readonly type: "chunk";
        readonly isEntry: boolean;
        readonly facadeModuleId: string | null;
        readonly imports: readonly string[];
        readonly dynamicImports: readonly string[];
        readonly modules: Readonly<Record<string, unknown>>;
      }
    | { readonly type: "asset" }
  >
>;

/**
 * The modules that `addon` matches which load without their add-on: in a chunk the entry reaches
 * through every import but a dynamic one of an add-on's own chunk. An add-on imported statically,
 * rather than loaded, is in such a chunk, so it is one of them.
 */
export function loadedWithout(bundle: Bundled, addon: RegExp): string[] {
  const counted = new Set<string>();
  const count = (file: string) => {
    const chunk = bundle[file];
    if (counted.has(file) || chunk?.type !== "chunk") {
      return;
    }
    counted.add(file);
    chunk.imports.forEach(count);
    for (const loaded of chunk.dynamicImports) {
      const target = bundle[loaded];
      if (!(target?.type === "chunk" && ADDON.test(target.facadeModuleId ?? ""))) {
        count(loaded);
      }
    }
  };
  for (const [file, chunk] of Object.entries(bundle)) {
    if (chunk.type === "chunk" && chunk.isEntry) {
      count(file);
    }
  }
  return [...counted].flatMap((file) => {
    const chunk = bundle[file];
    return chunk?.type === "chunk" ? Object.keys(chunk.modules).filter((id) => addon.test(id)) : [];
  });
}
