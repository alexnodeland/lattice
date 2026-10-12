# portalr's test application, which its acceptance tests run against (tests/app/main.py). Build it
# from lattice's root, which holds the one uv.lock: portalr's compose.yaml does. The UIs must be
# built first (`moon run app:build admin:build`); Dockerfile.dockerignore lets them in.

FROM ghcr.io/astral-sh/uv:0.12-python3.12-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY . .
RUN uv sync --locked --no-dev --package portalr --group app

WORKDIR /app/packages/portalr
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "tests.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
