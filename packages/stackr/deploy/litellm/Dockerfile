# stackr-litellm: the LiteLLM proxy compose.yaml pins, with stackr's configuration in it, for the
# AWS recipe's Fargate task (RFC-0004, ADR-0034). Built from lattice's root (deploy/build-images).
FROM ghcr.io/berriai/litellm-non_root:v1.103.0@sha256:fda2894415d89350ca6a16195c935726382354d2194ebb1ce43e6bd5480b06ce
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --chmod=a=rX packages/stackr/deploy/litellm/config.yaml /etc/litellm/config.yaml
# The providers' model groups, which config.yaml includes (ADR-0045).
COPY --link --chmod=a=rX packages/stackr/deploy/litellm/groups/providers.yaml /etc/litellm/groups.yaml
CMD ["--config", "/etc/litellm/config.yaml", "--port", "4000"]
