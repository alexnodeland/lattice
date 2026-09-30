# oncall, reflexr's reference app, as the contributor Compose file's `app` profile runs it.
# Build it from lattice's root, which holds the one uv.lock: `moon run reflexr:app-up`
# does, through reflexr's compose.yaml. Dockerfile.dockerignore, beside this file, lets
# in what it installs.

FROM ghcr.io/astral-sh/uv:0.12-python3.12-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY . .
RUN uv sync --locked --no-dev --package oncall

ENV PATH="/app/.venv/bin:$PATH" ONCALL_HOST=0.0.0.0 ONCALL_PORT=8000
EXPOSE 8000
CMD ["oncall-serve"]
