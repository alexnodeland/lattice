/**
 * A link as an `href`, only if it is an address a browser opens as a page: http or https. Anything
 * else, a `javascript:` or `data:` address, or text that is no address, is none, so a link is never
 * a way to run what a server, or a tool's setting, put in it.
 */
export function safeHref(link: string | null | undefined): string | null {
  // Written as an authority, `http://`: a browser reads `http:foo` as `http://foo/`, and a link
  // that isn't written so is not one a server of ours makes.
  if (!link || !/^https?:\/\//.test(link)) {
    return null;
  }
  try {
    const { protocol } = new URL(link);
    return protocol === "http:" || protocol === "https:" ? link : null;
  } catch {
    return null;
  }
}
