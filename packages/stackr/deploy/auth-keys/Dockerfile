# stackr-auth-keys: scripts/auth-keys, for the AWS recipe's one-off task (RFC-0004, ADR-0034), which
# writes GoTrue's key set and the service role's key to their secrets. Its dependencies are
# stackr's auth-keys group, as lattice's uv.lock pins them, installed by uv into the Python it runs
# on. Built from lattice's root (deploy/build-images).
FROM python:3.13.16-slim-trixie@sha256:cf50a4f6ac4f026458b08d5222023d700ac806410dff5e9ca8728fa44f2b850f AS build

# The release's build time (deploy/image-archive): with it, Python writes each .pyc against its
# source's hash, not its time, which BuildKit's rewrite-timestamp would leave stale.
ARG SOURCE_DATE_EPOCH
COPY --from=ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python
COPY . .
# Read-only for everyone, directories and all, here: a COPY's --chmod of a tree leaves its
# directories to the builder, and where nobody can't read pyvenv.cfg, Python ignores the venv.
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-install-workspace --package stackr --only-group auth-keys \
  && chmod -R a=rX /app/.venv

FROM python:3.13.16-slim-trixie@sha256:cf50a4f6ac4f026458b08d5222023d700ac806410dff5e9ca8728fa44f2b850f
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

# Nothing here installs packages: pip goes.
RUN rm -rf /usr/local/bin/pip* /usr/local/lib/python3.13/site-packages/pip*
COPY --link --from=build /app/.venv /app/.venv
COPY --link --chmod=a=rX packages/stackr/scripts/auth-keys packages/stackr/scripts/_auth_keys.py /app/
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["/app/.venv/bin/python", "/app/auth-keys"]
