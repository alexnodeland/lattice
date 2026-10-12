# ADR-0014: portalr's and grantr's marks

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0001](0001-lattices-brand.md#the-familys-inks) reserved the last inks for the two packages still to come: cyan, magenta and yellow together for portalr, the full-colour proof, and yellow and key for grantr, since grants are keys. It drew neither mark, and named the problem each would meet. portalr's three inks overprint only into its siblings' indigo, red and green, so none of its overlaps is its own, and six colours are busy at 16 pixels. grantr's yellow and key overprint into a near-black beside stackr's key. Each needs a working colour of its own, and portalr needs two versions of its mark, for its `app` and `admin` UIs.

[lattice RFC-0002](../rfcs/0002-portalr-the-portal.md#the-brand) gave both marks to its phase 2, with the tokens they bring for portalr's `ui`. Both packages are now in lattice. Six candidates were drawn to the family's system, with every overlap computed: three for each package. The maintainer chose one of each.

## Decision

### portalr: Ajar

- **The mark is lattice's cell with one side open.** Three of the cell's four sides remain, each on one process ink, cyan, magenta and yellow. The portal is a window onto the lattice the family is drawn on, opened.
- **The two versions open to opposite sides.** `app`'s opens to the upper right, outward, into the system. `admin`'s opens to the lower left, the side the operators stand on. Both keep the cyan side, upper left, and the yellow one, lower right.
- **Its working colour is chosen, not overprinted: a violet,** `#6B2FA0` on paper and `#E2CCF5` on screen. It fills the overlaps, where two sides cross, as every sibling's overprint does. No sibling works in it.

| Colour | Light | Dark | Contrast |
|---|---|---|---|
| Cyan, magenta, yellow | `#009FE3`, `#E4007C`, `#FFC400` | `#38C6F4`, `#FF4DA6`, `#FFD54A` | The plates; never text |
| Violet, the overprint and working colour | `#6B2FA0` | `#E2CCF5` | 8.27:1 on `#FFFFFF`, 7.60:1 on its paper; 12.06:1 on `#0D1920`, 12.49:1 on its paper |
| Paper | `#F7F4FB` | `#17111F` | |
| Graphite | `#5E5470` | `#BDB2CC` | 6.48:1 and 9.16:1 on the papers |

### grantr: Shield

- **The mark is a shield:** artifactr's caret turned over, in key, and a slab across its top, in yellow, whose ends are cut along the arms' outer edges. Where the slab crosses each arm, and where the arms cross at the foot, is the overprint.
- **Its working colour is a dark gold,** `#6B5300` on paper and `#FFF6D6` on screen: yellow's own shade, chosen within the set rather than the near-black yellow and key would make.
- **On dark backgrounds the key plate is stackr's tint,** `#8C8E9E`, so the pale overprint and the yellow stand apart from it. On light backgrounds it is key, `#1C1D26`.

| Colour | Light | Dark | Contrast |
|---|---|---|---|
| Yellow, key | `#FFC400`, `#1C1D26` | `#FFD54A`, `#8C8E9E` | The plates; never text |
| Dark gold, the overprint and working colour | `#6B5300` | `#FFF6D6` | 7.34:1 on `#FFFFFF`, 6.90:1 on its paper; 16.49:1 on `#0D1920`, 16.56:1 on its paper |
| Paper | `#FAF8F0` | `#1A170C` | |
| Graphite | `#625A45` | `#C4BBA3` | 6.44:1 and 9.37:1 on the papers |

### Both

- **The files follow the family's layout,** in `docs/portalr/assets/brand/` and `docs/grantr/assets/brand/`: marks, lockups, banners, favicons and `tokens.json`. portalr's `admin` mark has its own files and favicon.
- **A lockup ends 8 units below its descender.** The family's lockup ends 8 units below the baseline, which clips relayr's `y`. "portalr" and "grantr" descend too, so their lockups are taller by the descender.
- **portalr's tokens become `ui`'s CSS custom properties,** in `packages/portalr/web/ui/src/tokens.css`, light and dark, which Tailwind's `@theme` takes as its theme.
- **The family sheet shows eight marks,** and the brand page states both. This amends ADR-0001's reservations: the inks were reserved there, and the marks and working colours are recorded here.

## Options considered

| Package | Candidate | Working colour | Why not, or what it costs |
|---|---|---|---|
| portalr | **Ajar: lattice's cell, one side open (chosen)** | Violet `#6B2FA0` | Reads as lattice's child, which suits the portal onto the family. Its violet is a step from artifactr's indigo |
| portalr | Register: three plates rising in steps | Orange `#C2410C` | Five colours at 16 pixels, with overprints a pixel wide, and it reads as signal bars. Its `admin` version was only a mirror. The orange is close to reflexr's red |
| portalr | Aperture: three blades round an open centre | Sepia `#7A3E14` | Three strokes on three directions close into a triangle, so it carries ADR-0001's objection to Diagram: a delta, or an A |
| grantr | Key: a shaft with two yellow teeth | Ochre `#7A5600` | Reads as a reversed F, or a flag, before it reads as a key |
| grantr | Gate: two posts and a bar on reflexr's diagonal | Slate `#474A5E` | Reads as a hash or a ladder, and the slate is a tint of key, beside stackr's greys |
| grantr | **Shield: a slab over the caret turned over (chosen)** | Dark gold `#6B5300` | Its inverted triangle is near evalr's tick, and it borrows artifactr's caret and stackr's slab |

## Consequences

- Easier: every member of the family has its mark, its inks and a working colour no sibling uses. portalr's UIs and the site share one set of tokens.
- Easier: portalr's two UIs are told apart by their mark's open side, in their favicons and headers, without a second colour.
- Harder: Ajar is lattice's cell with a side taken away, and at 16 pixels it reads as a broken ring before it reads as a window. The drawing keeps it apart from lattice: three inks where lattice has one, an open side where lattice's is closed, and violet overlaps where lattice's are deep cyan. Its open ends keep lattice's points rather than flat cuts.
- Harder: portalr's violet sits between artifactr's indigo and relayr's deep magenta. It is lighter and redder than the indigo (1.39:1 between them), and the two marks share no shape, but in a tab strip their colours are close.
- Harder: Shield borrows two siblings' shapes, and its inverted triangle is near evalr's tick. The drawing keeps it apart: both arms reach the top of the grid, where evalr's tick cuts one short; it is symmetric, where the tick leans; it is in key and yellow, where the tick is in yellow and cyan; and the slab across its top closes it as no sibling is closed.
- Harder: grantr's dark gold is yellow's shade, so on paper the overprint is lighter than the key it crosses, where the family's overprints are darker than both inks.

## Action items

1. [x] The brand files, the family sheet and the brand pages.
2. [x] portalr's `ui` tokens, and its first primitives on them.
