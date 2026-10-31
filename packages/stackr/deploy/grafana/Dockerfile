# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# stackr-grafana: the Grafana compose.yaml pins, with stackr's provisioning and the dashboards of
# stackr, artifactr and reflexr in it, as compose.yaml mounts them, for the AWS recipe's Fargate
# task (RFC-0004, ADR-0034). Its data sources' addresses come from the environment: Compose's names
# by default. Built from lattice's root (deploy/build-images), and by compose.yaml, so one machine
# runs the same image. It carries ClickHouse's data source plugin (ADR-0048), fetched as the image
# is built, pinned by version and by each architecture's sha256, and signed by Grafana Labs: it
# loads without a network, and no unsigned plugin is allowed.

# The plugin's archive for each architecture the image is built for. Renovate lists a new version
# on its Dependency Dashboard (renovate.json's grafana-plugins), and opens a pull request only when
# it is ticked there; that pull request moves the version in the URL alone, and fails the check
# below until both digests move with it. To move it, take the version and each architecture's
# sha256 from grafana.com's list of its versions
# (https://grafana.com/api/plugins/grafana-clickhouse-datasource/versions/<version>, `packages`),
# and check each against the download itself:
#   curl -fsSL '<the URL below, at the new version, os and arch>' | sha256sum
# Fetched with curl, not ADD (ADR-0051): ADD has no timeout, and one stalled download held CI for minutes
# before it failed. Each try is bounded, a failed one is tried again, and the archive is checked
# against its sha256 before anything uses it, as ADD's --checksum did. The curl image is the one
# compose.yaml pins.
FROM --platform=$BUILDPLATFORM curlimages/curl:8.22.0@sha256:58adaa4e8dca9c988bae2aba4ab3434a0bb2da16bbe3f92dec39ec7785166777 AS clickhouse-plugin
ARG TARGETARCH
WORKDIR /tmp
RUN case "$TARGETARCH" in \
      amd64) sha256=fc8b4a4ff71e7db614a3560e5b5678bbab523578abca280a195e0bd30d9a52d5 ;; \
      arm64) sha256=c9140657df5c87d1736cee522dd4f213395138fa88c84559660376f3b609a8a5 ;; \
      *) echo "no ClickHouse plugin pinned for $TARGETARCH" >&2; exit 1 ;; \
    esac && \
    curl --fail --silent --show-error --location --connect-timeout 10 --max-time 120 \
      --retry 4 --retry-delay 5 --retry-all-errors --output plugin.zip \
      "https://grafana.com/api/plugins/grafana-clickhouse-datasource/versions/4.22.1/download?os=linux&arch=$TARGETARCH" && \
    echo "$sha256  plugin.zip" | sha256sum -c -

FROM grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

ENV PROMETHEUS_ADDRESS=prometheus \
    TEMPO_ADDRESS=tempo \
    LOKI_ADDRESS=loki \
    PYROSCOPE_ADDRESS=pyroscope \
    CLICKHOUSE_ADDRESS=clickhouse \
    GF_PATHS_PLUGINS=/usr/share/grafana/plugins-baked \
    GF_PLUGINS_PREINSTALL_DISABLED=true \
    GF_ANALYTICS_REPORTING_ENABLED=false \
    GF_ANALYTICS_CHECK_FOR_UPDATES=false \
    GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false \
    GF_NEWS_NEWS_FEED_ENABLED=false
# Outside /var/lib/grafana, so the data volume Compose mounts there doesn't hide it.
USER root
RUN --mount=type=bind,from=clickhouse-plugin,source=/tmp/plugin.zip,target=/tmp/plugin.zip \
    mkdir -p /usr/share/grafana/plugins-baked && \
    unzip -q /tmp/plugin.zip -d /usr/share/grafana/plugins-baked && \
    chmod -R a=rX /usr/share/grafana/plugins-baked && \
    chmod a+x /usr/share/grafana/plugins-baked/grafana-clickhouse-datasource/gpx_clickhouse_linux_*
USER grafana
# Not --link: that would make /var/lib/grafana, Grafana's own, root's.
COPY --chmod=a=rX packages/stackr/deploy/grafana/provisioning/datasources /etc/grafana/provisioning/datasources
COPY --chmod=a=rX packages/stackr/deploy/grafana/provisioning/dashboards /etc/grafana/provisioning/dashboards
COPY --chmod=a=rX packages/stackr/deploy/grafana/dashboards/stackr /var/lib/grafana/dashboards/stackr
COPY --chmod=a=rX packages/artifactr/deploy/grafana/dashboards /var/lib/grafana/dashboards/artifactr
COPY --chmod=a=rX packages/reflexr/deploy/grafana/dashboards /var/lib/grafana/dashboards/reflexr
