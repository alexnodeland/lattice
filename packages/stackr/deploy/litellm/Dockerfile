# stackr-litellm: the LiteLLM proxy compose.yaml pins, with stackr's configuration in it, for the
# AWS recipe's Fargate task (RFC-0004, ADR-0034). Built from lattice's root (deploy/build-images).
FROM ghcr.io/berriai/litellm:v1.103.0@sha256:bd089afdcd35b894b14a93f9743cdc8b591f82da1a38dd43a010a7b0c9de5fd7

COPY packages/stackr/deploy/litellm/config.yaml /etc/litellm/config.yaml
CMD ["--config", "/etc/litellm/config.yaml", "--port", "4000"]
