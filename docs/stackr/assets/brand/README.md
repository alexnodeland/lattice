# Brand

stackr is one of a family of four projects: [artifactr](https://github.com/alexnodeland/artifactr), [reflexr](https://github.com/alexnodeland/reflexr), [evalr](https://github.com/alexnodeland/evalr) and stackr. Their marks are drawn on one 64-unit grid, with one stroke and one diagonal, their wordmarks are set in one typeface, and each has a colour of its own. The family's identity comes from print proofing: each library is drawn in two of the three process inks, cyan, magenta and yellow, and where both land on the same spot they overprint into a third colour, its working colour. reflexr's [brand page](https://github.com/alexnodeland/reflexr/blob/main/docs/assets/brand/README.md) states the system in full.

stackr prints in **key**, the fourth plate: the black that the colour plates are printed in register to, and the quiet layer they sit on. Its mark is **three slabs**, stacked along the family's diagonal, with their ends cut at its angle: the layers the libraries run on. The slabs are one tint of key, and where two layers overlap they print in full key, the family's overprint drawn without a hue.

<p>
  <img src="mark-light.svg#gh-light-mode-only" width="96" alt="The stackr mark">
  <img src="mark-dark.svg#gh-dark-mode-only" width="96" alt="The stackr mark">
</p>

## Files

Every file is a hand-authored SVG with no embedded images or fonts. Text is outlined, so nothing depends on the viewer's fonts.

| File | What it is | Use it on |
|---|---|---|
| [`mark-light.svg`](mark-light.svg) | The mark | Light backgrounds |
| [`mark-dark.svg`](mark-dark.svg) | The mark, with a light overprint | Dark backgrounds |
| [`lockup-light.svg`](lockup-light.svg) | The mark and the wordmark | Light backgrounds |
| [`lockup-dark.svg`](lockup-dark.svg) | The mark and the wordmark | Dark backgrounds |
| [`banner-light.svg`](banner-light.svg) | The README banner, 1280 × 400 | Light backgrounds |
| [`banner-dark.svg`](banner-dark.svg) | The README banner, 1280 × 400 | Dark backgrounds |
| [`favicon.svg`](favicon.svg) | The mark, switching to the dark colours when the system prefers a dark scheme | Browser tabs |
| [`tokens.json`](tokens.json) | The colours below, and the site's, as data | Tools and new material |

lattice's site applies one palette to every section, from its `docs/assets/stylesheets/lattice.css`, until lattice's brand ADR.

The banners place the mark three grid units (21.6) left of the family's banner origin, at (824, 0.8) rather than (845.6, 0.8). At the family's placement, the top slab's right end ran past the panel's edge and its cut was lost; now all three slabs are whole, with the same room on either side of them. Nothing else about the banner differs from the family's layout.

## Colours

| Name | Light | Dark | Role |
|---|---|---|---|
| Key tint | `#6A6C7C` | `#8C8E9E` | The slabs. The site's interactive accent and code highlights on light backgrounds; code highlights on dark ones. |
| Key | `#1C1D26` | `#F1F1F6` | Where two slabs overlap, the wordmark, and the site's primary colour for headings and links (`#D9DAE3` for links on dark backgrounds). On dark backgrounds, the site's interactive accent. |
| Paper | `#F5F5F7` | `#15161B` | Backgrounds of the banner, and of the site's dark scheme. |
| Graphite | `#5C5E6B` | `#A7A9B6` | Secondary text, such as the banner's tagline. |

On paper, key printed over its own tint makes a darker colour, so the light overlaps are near-black. On screen, overlapping light makes a lighter one, so on dark backgrounds the overlaps are near-white. Keep that logic when drawing new material in the brand's colours. Every colour used for text has a contrast of at least 4.5:1 against the background it is used on.

## Type

| Typeface | Role | Why |
|---|---|---|
| [Schibsted Grotesk](https://fonts.google.com/specimen/Schibsted+Grotesk) | The wordmark (Bold, outlined, tracked −1.2%), headings and body text on the site | The family's typeface: a plain, readable grotesque with an editorial voice |
| [Fragment Mono](https://fonts.google.com/specimen/Fragment+Mono) | Code on the site | A monospace in the Helvetica tradition, so code sits comfortably beside the grotesque |

Both are open-source (SIL Open Font License) and served by Google Fonts. The wordmark is always lowercase: **stackr**.

## Using the brand

- Use the light files on light backgrounds and the dark files on dark ones; don't recolour them.
- Keep clear space around the mark of at least a quarter of its height.
- The mark stays legible down to 16 pixels. Below 24 pixels, use it without the wordmark.
- stackr has no hue, so its colour can't tell a link from the text around it: links on the site are underlined, and should be wherever stackr's colours set text.
- Keep stackr in key beside its siblings. Its colour is the absence of one: don't borrow a library's ink to make it stand out.
- Don't stretch, rotate, outline or add effects to the mark, and don't set the wordmark in another typeface.
- In a README, switch between the light and dark banners with a `<picture>` element, as the repository's README does.

## Known weaknesses

- **Three horizontal bars can read as a menu icon.** The slant and the overlaps set it apart at the size of the lockup; at 16 pixels, in a tab strip, it is the family's least distinctive mark.
- **Without a hue, the site's links rely on their underline**, and its accent on weight and position more than colour.
