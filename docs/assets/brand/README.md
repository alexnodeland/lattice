# Brand

lattice holds the family's packages, and its identity is drawn in the family's system, which comes from print proofing. [ADR-0001](../../adr/0001-lattices-brand.md) records it. lattice prints on one plate, **cyan**: the ink artifactr and evalr share, and the hue of the blue that layout grids were printed in. Its mark is **one cell of the lattice** that every mark in the family is drawn on: four strokes on the family's two diagonals, artifactr's and reflexr's, which are square to each other. Where the cell's sides cross, the plate prints twice, into a deep cyan: lattice's working colour.

<p>
  <img src="mark-light.svg#gh-light-mode-only" width="96" alt="The lattice mark">
  <img src="mark-dark.svg#gh-dark-mode-only" width="96" alt="The lattice mark">
</p>

## Files

Every file is an SVG with no embedded images or fonts. Text is outlined, so nothing depends on the viewer's fonts.

| File | What it is | Use it on |
|---|---|---|
| [`mark-light.svg`](mark-light.svg) | The mark | Light backgrounds |
| [`mark-dark.svg`](mark-dark.svg) | The mark, with a light overprint | Dark backgrounds |
| [`lockup-light.svg`](lockup-light.svg) | The mark and the wordmark | Light backgrounds |
| [`lockup-dark.svg`](lockup-dark.svg) | The mark and the wordmark | Dark backgrounds |
| [`banner-light.svg`](banner-light.svg) | The README banner, 1280 × 400 | Light backgrounds |
| [`banner-dark.svg`](banner-dark.svg) | The README banner, 1280 × 400 | Dark backgrounds |
| [`favicon.svg`](favicon.svg) | The mark, switching to the dark colours when the system prefers a dark scheme | Browser tabs |
| [`family-light.svg`](family-light.svg) | The six marks of the family, over their names | Light backgrounds |
| [`family-dark.svg`](family-dark.svg) | The six marks of the family, over their names | Dark backgrounds |
| [`tokens.json`](tokens.json) | The colours below, and the site's, as data | Tools and new material |

The site's colours are applied from [`lattice.css`](../stylesheets/lattice.css), to every section: lattice's palette is the site's, and each package's banner and lockup open its own section.

## Colours

| Name | Light | Dark | Role |
|---|---|---|---|
| Cyan | `#009FE3` | `#38C6F4` | The plate: the cell's four sides. Code highlights on the site, and its interactive accent (`#0077B6` on light backgrounds, for contrast with text). |
| Overprint | `#005A87` | `#D9F2FD` | Where the plate prints twice: the cell's corners, the wordmark, and the site's primary colour and its links (`#8AD3F5` for links on dark backgrounds). |
| Paper | `#F3F8FA` | `#0F1B22` | Backgrounds of the banner. The site's dark scheme uses `#0D1920`. |
| Graphite | `#4D6573` | `#A0BCCB` | Secondary text, such as the banner's tagline. |

On paper, cyan printed over cyan makes a deeper cyan, so the light corners are a deep petrol blue. On screen, overlapping light makes a lighter colour, so on dark backgrounds the corners are a pale cyan. Keep that logic when drawing new material in the brand's colours. Every colour used for text has a contrast of at least 4.5:1 against the background it is used on: the overprint is 6.98:1 on paper and 7.47:1 on white, the accent 4.87:1 on white, and the dark scheme's link colour 10.80:1 on its background.

## Type

| Typeface | Role | Why |
|---|---|---|
| [Schibsted Grotesk](https://fonts.google.com/specimen/Schibsted+Grotesk) | The wordmark (Bold, outlined, tracked −1.2%), headings and body text on the site | The family's typeface: a plain, readable grotesque with an editorial voice |
| [Fragment Mono](https://fonts.google.com/specimen/Fragment+Mono) | Code on the site | A monospace in the Helvetica tradition, so code sits comfortably beside the grotesque |

Both are open-source (SIL Open Font License) and served by Google Fonts. The wordmark is always lowercase: **lattice**.

## Using the brand

- Use the light files on light backgrounds and the dark files on dark ones; don't recolour them.
- Keep clear space around the mark of at least a quarter of its height.
- The mark stays legible down to 16 pixels. Below 24 pixels, use it without the wordmark.
- Cyan is the grid, so don't use it as decoration. Outside the mark, it only marks interaction on the site (a hovered link, the current page) and highlights code; the overprint is the working colour for everything else.
- Don't stretch, rotate, outline or add effects to the mark, and don't set the wordmark in another typeface.
- A package's section on the site opens with that package's lockup, and its own brand page holds its colours. lattice's colours are the site's.
- In a README, switch between the light and dark banners with a `<picture>` element, as the repository's README does.

## The family

artifactr, reflexr, evalr, relayr and stackr share one brand system, and lattice, which holds them, is drawn in it too, so that they read as a family wherever they appear together: a README that links its siblings, a stack that runs them all, a system built from them.

<p>
  <img src="family-light.svg#gh-light-mode-only" width="100%" alt="The marks of artifactr, reflexr, evalr, relayr, stackr and lattice, over their names">
  <img src="family-dark.svg#gh-dark-mode-only" width="100%" alt="The marks of artifactr, reflexr, evalr, relayr, stackr and lattice, over their names">
</p>

### The system

- **The inks are a printer's**: cyan, magenta, yellow and key. artifactr, reflexr and evalr each print with two of the three process inks and name their own meaning for each, and where the two overlap they overprint into a third colour: the library's working colour. Any two of those three share one ink, as neighbouring jobs on a press share a plate. stackr prints in key. relayr and lattice each print on one plate, magenta and cyan, and their working colour is where that plate prints twice. portalr will print in all three process inks together, and grantr in yellow and key: [ADR-0001](../../adr/0001-lattices-brand.md#the-familys-inks) reserves them.
- **One grid.** Every mark is drawn on a 64-unit square and sits in the same place on it in every file, so one mark can replace another without re-spacing a layout.
- **One stroke.** A stroke is a band 14 units wide, measured horizontally, on artifactr's diagonal of 27 across for every 52 down (about 62.6°). Strokes end in flat cuts along the grid, and meet in points where one stroke's edge cuts the other. reflexr's diagonal, the caret's turned a quarter, runs 52 across for every 27 down and is square to artifactr's; a stroke on it is 14 units measured vertically.
- **One overprint.** A mark's overlaps, and only those, are filled with its overprint colour. On paper the overprint is darker than both inks, and on screen lighter.
- **One typographic layout.** The wordmark is Schibsted Grotesk Bold, lowercase, outlined and tracked 1.2% tight. In a lockup it is set at 64 units, with the mark's grid scaled so that 52 grid units (from line 6 to line 58, the height of artifactr's caret) are 0.8 of the type size, line 58 on the baseline, 0.16 of the type size between the mark and the word, and 8 units of padding. A banner is 1280 × 400 with 24-unit corners: the wordmark at 136 units (baseline 196, from x = 104), a two-line tagline in the same face at weight 420 and 32 units (baselines 272 and 316, from x = 108) in the graphite, and the mark at 7.2 times its grid from (845.6, 0.8), running off the panel.
- **One site palette rule.** The overprint is the working colour (links, and the theme's primary colour; headings stay in the text colour), the darker ink marks interaction, and the lighter ink highlights code. The dark scheme's background is a near-black of the overprint's hue.

### The siblings

| Name | Mark | Inks | Overprint | What the mark says |
|---|---|---|---|---|
| **[artifactr](../../artifactr/assets/brand/README.md)** | A caret, `^` | Magenta and cyan: a person and an agent | Indigo `#2D2A8C`: the artifact they share | The proofreader's sign for "insert here", and the letter A |
| **[reflexr](../../reflexr/assets/brand/README.md)** | A chevron, `>`: the caret turned a quarter | Yellow and magenta: an event and a response | Red `#B3122E`: the rule firing | A reflex, a signal in and bent back out; and "then" |
| **[evalr](../../evalr/assets/brand/README.md)** | A tick: the caret turned over, one arm cut short at two thirds of its height | Yellow and cyan: a person's judgement and an evaluator's | Green `#00704F`: the verdict where they agree | A verdict; its arms meet in a point, as the caret's do |
| **[relayr](../../relayr/assets/brand/README.md)** | Two strokes on the family's diagonal, each two thirds of the grid's height and half a stroke apart | Magenta alone: one plate, the ink artifactr and reflexr share | Deep magenta `#9E0A5E`, where the plate prints twice | The bridge between artifactr and reflexr, in the ink they share |
| **[stackr](../../stackr/assets/brand/README.md)** | Three slabs, stacked along the family's diagonal, their ends cut at its angle | Key: one tint for every layer | Key `#1C1D26`, where two layers overlap | The layers the other libraries run on, and the key plate the others are printed in register to |
| **lattice** | A cell of the lattice: four strokes on the family's two diagonals, meeting in points | Cyan alone: one plate, the ink artifactr and evalr share | Deep cyan `#005A87`, where the plate prints twice | The grid every mark is drawn on, and the repository that holds them |
| **portalr** | Not yet drawn | Cyan, magenta and yellow together: the full-colour proof | Not yet drawn | Reserved: one window onto every library, in two versions, for its `app` and `admin` UIs |
| **grantr** | Not yet drawn | Yellow and key: a nod to the key plate, since grants are keys | Not yet drawn | Reserved: identity and access for artifactr and reflexr |

portalr's and grantr's inks are reserved; neither package is in lattice yet. Their marks, their tokens (which become the UIs' CSS variables), and the two versions of portalr's mark are drawn in a later design, with their packages, from what the apps need.

### Known weaknesses

- **lattice's cell is the family's heaviest mark, and its only closed one.** Beside the siblings' open strokes it reads as a tile, and at 16 pixels as a ring or a tilted square before it reads as a lattice.
- **It has no flat cuts.** Every stroke ends where its neighbour's edge cuts it, which the stroke rule allows but no sibling does everywhere.
- **Cyan was the last single plate that can carry text** (magenta is relayr's, and yellow can't). That doesn't touch grantr or portalr, whose inks are a pair with key and the three-ink set, but a member after them can't print on one plate of its own: it prints in cyan or magenta with key, or shares a sibling's inks.
- **lattice's colours are close to its neighbours'.** The deep cyan sits between artifactr's indigo and evalr's green, and lattice's interactive accent, `#0077B6`, is evalr's. On the site the link colour and its hover are close, as relayr's are.
- **Neither reservation has an obvious colour of its own.** portalr's cyan, magenta and yellow overprint only into their siblings' indigo, red and green, and six colours are busy at 16 pixels, as Diagram's were. grantr's yellow and key overprint near-black, beside stackr's key, the reason relayr's ADR-0011 set aside indigo and red as a pair. Each could take a tint of key, as stackr does, or a colour chosen within its set; that is decided when they are drawn.
