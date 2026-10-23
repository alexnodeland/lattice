/**
 * What `rehype-raw` resolves to in portalr's builds: nothing. Streamdown imports `rehype-raw` to
 * offer HTML in Markdown, which portalr never passes it (`markdown.tsx` sanitizes alone), so the
 * plugin, parse5 and the entities package would be dead weight in every Markdown chunk (portalr
 * ADR-0040). Streamdown only compares its own plugins to this one, by identity, to choose what
 * it does with HTML; that choice is the same with this as with the real plugin, since portalr's
 * plugins never include either. Used, it would do nothing to the tree.
 */
export default function rehypeRaw(): undefined {
  return undefined;
}
