# ADR-0001: lattice's brand

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

lattice holds the family's packages and publishes their one site, at `https://lattice.alexnodeland.com`. [RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#docs) gives the site lattice's own header mark, favicon and palette, and leaves lattice's mark to a brand ADR. Until now the site has borrowed stackr's key palette and shown the theme's icon, and the repository's README has had no banner.

The family shares one brand system, stated on [reflexr's brand page](../reflexr/assets/brand/README.md#the-family): the printer's four inks, each coloured library printing in two of the three process inks that overprint into its working colour; one 64-unit grid; one stroke, 14 units wide on artifactr's diagonal of 27 across for 52 down; overlaps, and only overlaps, in the overprint; one typographic layout; and one rule for the site's palette. The inks are taken. artifactr prints in magenta and cyan, overprinting into indigo; reflexr in yellow and magenta, into red; evalr in yellow and cyan, into green. stackr prints in key, and relayr on one plate, magenta, which overprints itself into a deep magenta ([relayr ADR-0011](../relayr/adr/0011-documentation-site-and-brand.md)). Two more packages are planned, grantr and portalr, and will need marks of their own.

Three candidates were drawn to the system's rules, with every coordinate computed and every lockup, banner and family sheet set to the family's layout: Cell, Diagram and Register.

## Decision

- **lattice prints on one plate: cyan,** the ink artifactr and evalr share, as relayr prints on the ink artifactr and reflexr share. Cyan is also the hue of the non-reproducing blue that layout grids were printed in, which the process camera didn't see.
- **Its mark is one cell of the lattice that every mark in the family is drawn on.** The family has two diagonals: artifactr's, 27 across for 52 down, and reflexr's, the caret's turned a quarter, 52 across for 27 down. They are square to each other. Four strokes on them close into a cell: the steep sides 14 units wide measured horizontally, the shallow ones 14 units measured vertically, as reflexr's are, which is the same width square to each stroke. Each stroke ends where its neighbour's outer edge cuts it, so the cell's four corners are points, and they touch grid lines 6 and 58.
- **Where the cell's sides cross, the plate prints twice.** That overprint, a deep cyan, is lattice's working colour: `#005A87` on paper and `#D9F2FD` on screen. The mark says two things: the grid every mark in the family is drawn on, and the repository that holds them.
- **The files follow the family's layout to the unit,** and are in `docs/assets/brand/`. [The brand page](../assets/brand/README.md) states the colours, the type and their use, and, since lattice hosts the family, the system in full, the siblings with relayr and lattice added, and a family sheet with all six marks.
- **The site's palette comes from the tokens by the family's rule:** the overprint for headings and links, cyan (`#0077B6` on light backgrounds, for contrast) for interaction, cyan for code highlights, and a near-black of the overprint's hue, `#0D1920`, for the dark scheme's background. The header shows the mark, and the favicon switches with the system's scheme.

### The family's inks

With lattice on cyan, every member has its inks, and the two planned packages' are reserved now, before their marks are drawn:

| Member | Inks | Working colour |
|---|---|---|
| artifactr | Magenta and cyan | Indigo, where they overlap |
| reflexr | Yellow and magenta | Red, where they overlap |
| evalr | Yellow and cyan | Green, where they overlap |
| relayr | Magenta alone | Deep magenta, where the plate prints twice |
| stackr | Key | Key, where two layers overlap |
| lattice | Cyan alone | Deep cyan, where the plate prints twice |
| portalr (reserved) | Cyan, magenta and yellow together | Not yet drawn |
| grantr (reserved) | Yellow and key | Not yet drawn |

- **portalr prints in cyan, magenta and yellow together:** the full-colour proof, one window onto every library. portalr is the web app, an `app` UI for using the system and an `admin` UI, sharing `client` and `ui` packages.
- **grantr prints in yellow and key,** a nod to the key plate, since grants are keys.
- **Neither is in lattice yet.** Their marks, their tokens (which become the UIs' CSS variables), and the two versions of portalr's mark, for `app` and `admin`, are drawn with the portal and IAM RFC, from what the apps need.
- **Cell's cyan doesn't box them in.** The three pairs of process inks are artifactr's, reflexr's and evalr's, and with cyan both single plates that can carry text are taken, but the pairs with key and the three-ink set remain. grantr takes one pair with key and portalr the three inks; cyan with key and magenta with key are still free.

## Options considered

| Option | A working colour of its own | Within the system | At 16 pixels |
|---|---|---|---|
| **Cell: cyan alone, a cell of the lattice (chosen)** | Yes: a deep cyan, which no sibling works in | One plate, as relayr; nothing but the family's two diagonals | A clear ring, in both schemes |
| Diagram: the three process inks, a triangle | No: its overprints are its siblings' indigo, red and green, and its text is key | artifactr's caret, closed by stackr's slab | Six colours; a delta, or a filled-in A |
| Register: registration, a cross | No: registration shows on screen as key, so its colours are stackr's | A stroke on the diagonal, crossed by stackr's slab | A grey plus, beside stackr's grey slabs |

**Diagram** was drawn and set aside. It says the most: each of its sides is an ink two siblings share, and each corner overprints into a sibling's working colour, artifactr's indigo at the top and reflexr's red and evalr's green at the base; its magenta side joins artifactr to reflexr, as relayr does, and its base is stackr's slab. Its three inks are now portalr's, reserved above: a full-colour proof suits the portal, a window onto every library, more than the repository that holds them. And its two strokes are artifactr's mark polygon for polygon, so closed by the slab it reads as a delta or an A, and beside the wordmark as "Alattice". Six colours in a favicon is the flag that stackr's three-ink alternative was set aside for, and with no overprint of its own, its working colour would have been stackr's key.

**Register** was drawn and set aside. It is a registration mark's cross: the mark that every plate prints and every plate is aligned to, as one repository holds the packages to one lockfile, one CI and one release. But registration shows on screen as key, so in colour it is stackr's twin, and the site would have changed only in its header. A slanted cross reads as "add", or as a "t". A registration mark is a circle and a cross, and the family has no curves, so what is left is the least specific of the three.

## Consequences

- Easier: lattice's site has a colour of its own, and stops borrowing stackr's. The mark stays legible at 16 pixels, in both schemes.
- Easier: the family's system, its siblings and a sheet of every mark are in one place, on lattice's brand page, where the family's packages now live.
- Easier: the family's inks are allocated for every member, planned ones included, so the portal and IAM RFC starts from reserved inks.
- Harder, though not for grantr or portalr: no later member can print on one plate of its own. Cyan was the last single plate that can carry text (magenta is relayr's, and yellow can't), so a member after grantr and portalr prints in cyan or magenta with key, or shares a sibling's inks.
- Harder: cyan is the family's most shared ink: artifactr's, evalr's and lattice's now, and portalr's to come, as magenta is artifactr's, reflexr's and relayr's, and portalr's. The deep cyan sits between artifactr's indigo and evalr's green, lattice's interactive accent is evalr's, and on the site the link colour and its hover are close, as relayr's are.
- Harder: the cell is the family's heaviest mark and its only closed one. Beside the siblings' open strokes it reads as a tile, and at 16 pixels as a ring or a tilted square before it reads as a lattice.
- Harder: it has no flat cuts. Every stroke ends where its neighbour's edge cuts it, which the stroke rule allows but no sibling does everywhere.
- Harder: reflexr's family sheet shows four marks, and the packages' brand pages name four or five members; lattice's page is now where the family is stated in full.
