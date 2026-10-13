# stackr-auth-keys: scripts/auth-keys, for the AWS recipe's one-off task (RFC-0004, ADR-0034), which
# writes GoTrue's key set and the service role's key to their secret when it is empty. Its
# dependencies are stackr's auth-keys group, as lattice's uv.lock pins them. Built from lattice's
# root (deploy/build-images).
FROM ghcr.io/astral-sh/uv:0.12.24-python3.13-trixie-slim@sha256:adb723cc75f8a5fa33fa1928af0e032d9199694599c77ffeea5527a76e37a512 AS build

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY . .
RUN uv sync --locked --no-install-workspace --package stackr --only-group auth-keys

FROM python:3.13.16-slim-trixie@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --from=build /app/.venv /app/.venv
COPY --link --chmod=a=rX packages/stackr/scripts/auth-keys packages/stackr/scripts/_auth_keys.py /app/
ENV PATH="/app/.venv/bin:$PATH"
USER nobody
ENTRYPOINT ["python", "/app/auth-keys"]
