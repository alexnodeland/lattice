# stackr-otel-collector: the Collector compose.yaml pins, with stackr's configuration in it, for the
# AWS recipe's Fargate task (RFC-0004, ADR-0034), which can't mount a checkout. Built from lattice's
# root (deploy/build-images).
FROM otel/opentelemetry-collector-contrib:0.161.0@sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --chmod=a=rX packages/stackr/deploy/otel-collector/config.yaml /etc/otelcol-contrib/config.yaml
CMD ["--config=/etc/otelcol-contrib/config.yaml"]
