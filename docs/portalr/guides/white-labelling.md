# White-labelling the portal

A deployment can give portalr its product's look and name with a **brand kit**: a folder holding `brand.json` (the product's names, its words on the sign-in page, and its marks) and two token files, `tokens.light.json` and `tokens.dark.json`, in the W3C Design Tokens format. A kit names only what it changes over portalr's own look. The portal reads and checks the kit as it starts, and won't start with a fault in it ([lattice RFC-0007](../../rfcs/0007-portalr-brand-kits.md), [ADR-0056](../adr/0056-brand-kits-token-layers-loading-and-validation.md), [ADR-0057](../adr/0057-brand-kits-motion-and-tokens-as-the-only-override.md)).

## Start a kit

`portalr` is portalr's command line, installed with it; in an application from stackr's template, run it as `uv run portalr`.

```sh
portalr brand init my-kit
```

`init` starts a kit in a new, or empty, folder, and won't write over anything. By default it copies a plain kit to fill in: placeholder names and a square mark, and no tokens changed. `--from nightshade` or `--from calm` starts from one of portalr's two example kits instead: `nightshade` changes a few colours, and `calm` changes nearly everything (radii, shadows, motion, a different face), to show how far a kit reaches.

Beside the kit's own files, `init` writes:

- `tokens.reference.json`: portalr's default kit in full, light and dark, to look tokens up by their paths. The portal doesn't read it.
- `NOTICE`: what the kit carries, and under what terms.

## Change it

- **`brand.json`**: `identity.product`, `identity.app` and `identity.admin` are the names the UIs show in the header, the page titles, and the new-version notice; `copy.tagline` and `copy.signIn` are the sign-in page's words. `assets` names the marks, one for each scheme, and the favicon: SVG or PNG files inside the kit.
- **The token files**: copy a token's path from `tokens.reference.json` and give it a new `$value`. `tokens.dark.json` holds only what differs in the dark scheme from the light one.
- **Faces**: a kit may add its own faces, as WOFF2 files, each with its licence file in the kit.

## Check it

```sh
portalr brand validate my-kit
```

`validate` runs the portal's own checks and says every fault, one to a line: a token path the inventory hasn't got, a value its type can't take, text and its background under their contrast floor, motion outside its bounds, a mark that isn't a plain picture, a name with control characters in it. It reads only plain files of the kit's own: a link, even to another file in the kit, is refused, as the portal refuses it. `--json` says it as one JSON object instead: `ok`, the kit's `name` and `hash`, and its `faults`. It exits with 0 when the kit is one the portal can serve, 1 when it has faults or can't be read, and 2 when the command line is wrong, so it can run in CI. Text a kit wrote is escaped before it is printed, so a hostile kit can't forge a line of the log.

## Serve it

Pass the kit's folder to the router's site: `Site(..., brand=Path("my-kit"))` ([getting started](../getting-started.md#configjson)). In an application from stackr's template with the portal, `make brand` starts a kit in `brand/kit` (`make brand BRAND_FROM=nightshade` starts from an example), and checks it once it's there; set `PORTAL_BRAND_DIR=brand/kit` in `.env` to serve it. In the image the path is read under `/` (`brand/kit` is `/brand/kit`), so a kit the image serves lives in `brand/`. The image carries a copy of `brand/`, so `make up` and a single host serve the kit the image was built with: a changed kit needs a new image (`make up` builds one). Outside the template, a changed kit is rolled out by restarting the application.

## Not yet

- `portalr brand preview`, a page of every component and the motion playground against a kit, in both schemes: when it comes, a page run from a checkout of lattice, not part of the installed package.
- The pinned chrome tokens, so the skip link and a mini app's chrome still read the kit's roles.
- An `oklch()` colour, presets, and a kit per tenant: the full list is [RFC-0007's "Not yet"](../../rfcs/0007-portalr-brand-kits.md).
