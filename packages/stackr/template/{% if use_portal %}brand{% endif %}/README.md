# The brand kit

`make brand` starts the deployment's brand kit in `brand/kit` (lattice RFC-0007): its names and
words, its marks, and the tokens it changes over portalr's own look. `make brand` again checks it,
saying every fault. Set `PORTAL_BRAND_DIR=brand/kit` in `.env` to serve it. The image carries a
copy of this folder, so `make up` and a host serve the kit the image was built with: a changed
kit needs a new image, which `make up` builds. `make brand` runs `uv run portalr`, portalr's
command line, which the application's dependencies install.

The image reads `PORTAL_BRAND_DIR` under `/`, so a kit it serves is in this folder: `brand/kit`
is `/brand/kit` there. Docker copies the files with the permissions they have here, so under a
strict umask (077) make them readable to others (`chmod -R a+rX brand`), or the application,
which doesn't run as their owner, can't read them.

`make brand BRAND_FROM=nightshade` (or `calm`) starts from one of portalr's two example kits.
