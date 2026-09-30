# Brand

artifactr's identity comes from print proofing. Two inks, magenta and cyan, are the two participants: a person and an agent. Where both inks land on the same spot they overprint into a third colour, a deep indigo, which stands for the thing they share: the artifact. The mark is a proofreader's caret, the sign for "insert here", drawn as two strokes that meet at a shared tip. It also reads as the letter A.

<p>
  <img src="mark-light.svg#gh-light-mode-only" width="96" alt="The artifactr mark">
  <img src="mark-dark.svg#gh-dark-mode-only" width="96" alt="The artifactr mark">
</p>

## Files

Every file is a hand-authored SVG with no embedded images or fonts. Text is outlined, so nothing depends on the viewer's fonts.

| File | What it is | Use it on |
|---|---|---|
| [`mark-light.svg`](mark-light.svg) | The mark | Light backgrounds |
| [`mark-dark.svg`](mark-dark.svg) | The mark, with a light shared tip | Dark backgrounds |
| [`lockup-light.svg`](lockup-light.svg) | The mark and the wordmark | Light backgrounds |
| [`lockup-dark.svg`](lockup-dark.svg) | The mark and the wordmark | Dark backgrounds |
| [`banner-light.svg`](banner-light.svg) | The README banner, 1280 × 400 | Light backgrounds |
| [`banner-dark.svg`](banner-dark.svg) | The README banner, 1280 × 400 | Dark backgrounds |
| [`favicon.svg`](favicon.svg) | The mark, switching to the dark colours when the system prefers a dark scheme | Browser tabs |

## Colours

| Name | Light | Dark | Role |
|---|---|---|---|
| Magenta | `#E4007C` | `#FF4DA6` | One participant: the left stroke of the mark. The site's interactive accent (`#C2006A` on light backgrounds, for contrast with text). |
| Cyan | `#009FE3` | `#38C6F4` | The other participant: the right stroke of the mark. Code highlights on the site. |
| Overprint | `#2D2A8C` | `#E4E3FF` | The shared artifact: the mark's tip, the wordmark, and the site's primary colour for headings and links (`#B3B1FF` for links on dark backgrounds). |
| Paper | `#F6F6FB` | `#15142B` | Backgrounds of the banner. The site's dark scheme uses `#14132A`. |
| Graphite | `#5D5B80` | `#A3A2C8` | Secondary text, such as the banner's tagline. |

On paper, overlapping inks make a darker colour, so the light tip is deep indigo. On screen, overlapping light makes a lighter one, so on dark backgrounds the tip is a pale violet. Keep that logic when drawing new material in the brand's colours.

## Type

| Typeface | Role | Why |
|---|---|---|
| [Schibsted Grotesk](https://fonts.google.com/specimen/Schibsted+Grotesk) | The wordmark (Bold, outlined), headings and body text on the site | A grotesque drawn for a news publisher: plain and readable, with an editorial voice that suits a tool about editing |
| [Fragment Mono](https://fonts.google.com/specimen/Fragment+Mono) | Code on the site | A monospace in the Helvetica tradition, so code sits comfortably beside the grotesque |

Both are open-source (SIL Open Font License) and served by Google Fonts. The wordmark is always lowercase: **artifactr**.

## Using the brand

- Use the light files on light backgrounds and the dark files on dark ones; don't recolour them.
- Keep clear space around the mark of at least a quarter of its height.
- The mark stays legible down to 16 pixels. Below 24 pixels, use it without the wordmark.
- Magenta and cyan stand for the two participants, so don't use them as decoration. Outside the mark, magenta only marks interaction on the site (a hovered link, the current page), and the overprint indigo is the working colour for everything else.
- Don't stretch, rotate, outline or add effects to the mark, and don't set the wordmark in another typeface.
- In a README, switch between the light and dark banners with a `<picture>` element, as the repository's README does.
