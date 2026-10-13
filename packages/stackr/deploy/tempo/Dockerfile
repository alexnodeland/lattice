# stackr-tempo: the image compose.yaml pins, with stackr's configuration in it, for the AWS recipe's
# Fargate task (RFC-0004, ADR-0034), which can't mount a checkout. Its storage, a local volume or
# S3, comes from the environment. Built from lattice's root (deploy/build-images).
FROM grafana/tempo:3.0.3@sha256:0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --chmod=a=rX packages/stackr/deploy/tempo/tempo.yaml /etc/tempo/tempo.yaml
CMD ["-config.file=/etc/tempo/tempo.yaml", "-config.expand-env=true"]
