# Brand

reflexr's identity is a sibling of [artifactr's](../../../artifactr/assets/brand/README.md), and comes from the same place: print proofing. Two inks, yellow and magenta, are the two halves of a reflex: the event that arrives and the response that leaves. Where both inks land on the same spot they overprint into a third colour, a deep red, which stands for the moment between them: the rule firing. The mark is artifactr's caret turned a quarter, a chevron. An event comes in along the upper stroke and the response goes back out along the lower one, and at the point, where the two meet, the rule fires. It also reads as "then", the second half of every rule.

<p>
  <img src="mark-light.svg#gh-light-mode-only" width="96" alt="The reflexr mark">
  <img src="mark-dark.svg#gh-dark-mode-only" width="96" alt="The reflexr mark">
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
| [`family-light.svg`](family-light.svg) | The family's first four marks, over their names; [lattice's sheet](../../../assets/brand/README.md#the-family) has all six | Light backgrounds |
| [`family-dark.svg`](family-dark.svg) | The family's first four marks, over their names; [lattice's sheet](../../../assets/brand/README.md#the-family) has all six | Dark backgrounds |

lattice's site takes lattice's palette in every section ([lattice ADR-0001](../../../adr/0001-lattices-brand.md)), and opens reflexr's section with reflexr's lockup. Where the table below names a role on the site, it is the role reflexr's own palette gives that colour.

## Colours

| Name | Light | Dark | Role |
|---|---|---|---|
| Yellow | `#FFC400` | `#FFD54A` | The event: the upper stroke of the mark. Highlighted lines of code on the site. |
| Magenta | `#E4007C` | `#FF4DA6` | The response: the lower stroke of the mark. The site's interactive accent (`#C2006A` on light backgrounds, for contrast with text). |
| Overprint | `#B3122E` | `#FFE1DA` | The rule firing: the mark's point, the wordmark, and the site's primary colour for headings and links (`#FF9D93` for links on dark backgrounds). |
| Paper | `#FAF6F3` | `#221418` | Backgrounds of the banner. The site's dark scheme uses `#1F1317`. |
| Graphite | `#6E5055` | `#C4A8AC` | Secondary text, such as the banner's tagline. |

On paper, overlapping inks make a darker colour, so the light overprint is a deep red. On screen, overlapping light makes a lighter one, so on dark backgrounds the overprint is a pale rose. Keep that logic when drawing new material in the brand's colours. Every colour used for text has a contrast of at least 4.5:1 against the background it is used on.

## Type

| Typeface | Role | Why |
|---|---|---|
| [Schibsted Grotesk](https://fonts.google.com/specimen/Schibsted+Grotesk) | The wordmark (Bold, outlined, tracked 1.2% tight), headings and body text on the site | artifactr's face, so the family reads as one: a plain, readable grotesque with an editorial voice |
| [Fragment Mono](https://fonts.google.com/specimen/Fragment+Mono) | Code on the site | A monospace in the Helvetica tradition, so code sits comfortably beside the grotesque |

Both are open-source (SIL Open Font License) and served by Google Fonts. The wordmark is always lowercase: **reflexr**.

## Using the brand

- Use the light files on light backgrounds and the dark files on dark ones; don't recolour them.
- Keep clear space around the mark of at least a quarter of its height.
- The mark stays legible down to 16 pixels. Below 24 pixels, use it without the wordmark.
- Yellow and magenta stand for the event and the response, so don't use them as decoration. Outside the mark, magenta only marks interaction on the site (a hovered link, the current page), yellow only highlights code, and the overprint red is the working colour for everything else.
- Never set text in yellow: it is too light on paper.
- Don't stretch, rotate, outline or add effects to the mark, and don't set the wordmark in another typeface.
- In a README, switch between the light and dark banners with a `<picture>` element, as [reflexr's README](https://github.com/alexnodeland/lattice/blob/main/packages/reflexr/README.md) does.

## The family

artifactr, reflexr, evalr, relayr and stackr share one brand system with lattice, which holds them. [lattice's brand page](../../../assets/brand/README.md#the-family) states it in full: the inks, the grid, the stroke, the overprint and the layout every mark follows, each member's mark and inks, the inks reserved for portalr and grantr, and a family sheet with all six marks.

### Known weaknesses

- **The chevron reads as "play" or "next"** to some eyes, and in front of the wordmark it looks like a shell prompt. The family accepts this, as artifactr's caret also reads as "up", and for a library whose rules end in "then run this" the connotation is not wrong.
- **Yellow is the weakest ink on paper.** It holds at the size of the mark, and on dark backgrounds it is the strongest, but it must never carry text or thin lines.
- **Magenta is shared with artifactr, and with relayr, which prints in it alone.** Side by side, the shapes and overprints tell them apart, but in a browser's tab strip at 16 pixels reflexr and artifactr are the closest pair in the family, and relayr's deep magenta is the working colour nearest to reflexr's red.
