# Brand

evalr is one of the five packages in [lattice](https://github.com/alexnodeland/lattice), which is drawn in their brand system too: [artifactr](../../../artifactr/index.md), [reflexr](../../../reflexr/index.md), evalr, [relayr](../../../relayr/index.md) and [stackr](../../../stackr/index.md). Their marks are drawn on one 64-unit grid with one stroke, their wordmarks are set in one typeface, and each has a colour of its own. The family's identity comes from print proofing: artifactr, reflexr and evalr are each drawn in two of the three process inks, cyan, magenta and yellow, and where both land on the same spot they overprint into a third colour, the library's working colour (artifactr's magenta and cyan overprint into indigo); relayr and lattice each print on one plate, magenta and cyan, and stackr prints in key. [lattice's brand page](../../../assets/brand/README.md#the-family) states the system in full, with the inks it reserves for portalr and grantr.

evalr's hue is **green**. Its mark is a tick, the family's proofreader's caret turned over with one arm cut short. Its two inks are two judgements of the same thing: **yellow**, for people's, and **cyan**, for the evaluator's. Where they meet, at the point of the tick, they overprint into green: agreement, the verdict both give. Cyan is the ink evalr shares with artifactr.

<p>
  <img src="mark-light.svg#gh-light-mode-only" width="96" alt="The evalr mark">
  <img src="mark-dark.svg#gh-dark-mode-only" width="96" alt="The evalr mark">
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

lattice's site takes lattice's palette in every section ([lattice ADR-0001](../../../adr/0001-lattices-brand.md)), and opens evalr's section with evalr's lockup. Where the table below names a role on the site, it is the role evalr's own palette gives that colour.

## Colours

| Name | Light | Dark | Role |
|---|---|---|---|
| Yellow | `#FFC400` | `#FFD54A` | People's judgement: the short arm of the tick. Code highlights on the site. |
| Cyan | `#009FE3` | `#38C6F4` | The evaluator's judgement: the long arm of the tick. The site's interactive accent (`#0077B6` on light backgrounds, for contrast with text). |
| Overprint | `#00704F` | `#D8F5E6` | Agreement: the tick's point, the wordmark, and the site's primary colour for headings and links (`#72DCAE` for links on dark backgrounds). |
| Paper | `#F4F8F5` | `#101E19` | Backgrounds of the banner. The site's dark scheme uses `#0F1B16`. |
| Graphite | `#4F6B5D` | `#A2C4B3` | Secondary text, such as the banner's tagline. |

On paper, yellow printed over cyan makes a green darker than either, so the light point is a deep green. On screen, overlapping light makes a lighter colour, so on dark backgrounds the point is a pale green. Keep that logic when drawing new material in the brand's colours.

## Type

| Typeface | Role | Why |
|---|---|---|
| [Schibsted Grotesk](https://fonts.google.com/specimen/Schibsted+Grotesk) | The wordmark (Bold, outlined, tracked −1.2%), headings and body text on the site | The family's typeface: a plain, readable grotesque with an editorial voice |
| [Fragment Mono](https://fonts.google.com/specimen/Fragment+Mono) | Code on the site | A monospace in the Helvetica tradition, so code sits comfortably beside the grotesque |

Both are open-source (SIL Open Font License) and served by Google Fonts. The wordmark is always lowercase: **evalr**.

## Using the brand

- Use the light files on light backgrounds and the dark files on dark ones; don't recolour them.
- Keep clear space around the mark of at least a quarter of its height.
- The mark stays legible down to 16 pixels. Below 24 pixels, use it without the wordmark.
- Yellow and cyan stand for the two judgements, so don't use them as decoration. Outside the mark, cyan only marks interaction on the site (a hovered link, the current page) and yellow only highlights code; the overprint green is the working colour for everything else.
- Don't stretch, rotate, outline or add effects to the mark, and don't set the wordmark in another typeface.
- In a README, switch between the light and dark banners with a `<picture>` element, as [evalr's README](https://github.com/alexnodeland/lattice/blob/main/packages/evalr/README.md) does.
