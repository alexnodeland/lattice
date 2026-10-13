# stackr-auth-keys: scripts/auth-keys, for the AWS recipe's one-off task (RFC-0004, ADR-0034), which
# writes GoTrue's key set and the service role's key to their secrets. Its dependencies are
# stackr's auth-keys group, as lattice's uv.lock pins them, installed by uv into the Python it runs
# on. Built from lattice's root (deploy/build-images).
FROM python:3.13.16-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.24@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-install-workspace --package stackr --only-group auth-keys

FROM python:3.13.16-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

# Nothing here installs packages: pip goes.
RUN rm -rf /usr/local/bin/pip* /usr/local/lib/python3.13/site-packages/pip*
COPY --link --from=build --chmod=a=rX /app/.venv /app/.venv
COPY --link --chmod=a=rX packages/stackr/scripts/auth-keys packages/stackr/scripts/_auth_keys.py /app/
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
ENTRYPOINT ["/app/.venv/bin/python", "/app/auth-keys"]
