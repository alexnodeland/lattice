# stackr-loki: the image compose.yaml pins, with stackr's configuration in it, for the AWS recipe's
# Fargate task (RFC-0004, ADR-0034), which can't mount a checkout. Its storage, a local volume or
# S3, comes from the environment. Built from lattice's root (deploy/build-images).
FROM grafana/loki:3.7.8@sha256:1107dd5274e0ada47e42472b7a7e71f3b2a2fe878878108f3e2f9e51528f0193
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --chmod=a=rX packages/stackr/deploy/loki/loki.yaml /etc/loki/loki.yaml
CMD ["-config.file=/etc/loki/loki.yaml", "-config.expand-env=true"]
