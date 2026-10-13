# stackr-pyroscope: the image compose.yaml pins, with stackr's configuration in it, for the AWS recipe's
# Fargate task (RFC-0004, ADR-0034), which can't mount a checkout. Its storage, a local volume or
# S3, comes from the environment. Built from lattice's root (deploy/build-images).
FROM grafana/pyroscope:2.3.1@sha256:86a9ee7448487409ead8ada78789de7b78b739711b92b5d7224a1a54abf3eeb2
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --chmod=a=rX packages/stackr/deploy/pyroscope/config.yaml /etc/pyroscope/config.yaml
CMD ["-config.file=/etc/pyroscope/config.yaml", "-config.expand-env=true"]
