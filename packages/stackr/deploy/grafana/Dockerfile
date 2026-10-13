# stackr-grafana: the Grafana compose.yaml pins, with stackr's provisioning and the dashboards of
# stackr, artifactr and reflexr in it, as compose.yaml mounts them, for the AWS recipe's Fargate
# task (RFC-0004, ADR-0034). Its data sources' addresses come from the environment: Compose's names
# by default. Built from lattice's root (deploy/build-images).
FROM grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0

ENV PROMETHEUS_ADDRESS=prometheus \
    TEMPO_ADDRESS=tempo \
    LOKI_ADDRESS=loki \
    PYROSCOPE_ADDRESS=pyroscope \
    GF_ANALYTICS_REPORTING_ENABLED=false \
    GF_ANALYTICS_CHECK_FOR_UPDATES=false \
    GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false \
    GF_NEWS_NEWS_FEED_ENABLED=false
COPY packages/stackr/deploy/grafana/provisioning/datasources /etc/grafana/provisioning/datasources
COPY packages/stackr/deploy/grafana/provisioning/dashboards /etc/grafana/provisioning/dashboards
COPY packages/stackr/deploy/grafana/dashboards/stackr /var/lib/grafana/dashboards/stackr
COPY packages/artifactr/deploy/grafana/dashboards /var/lib/grafana/dashboards/artifactr
COPY packages/reflexr/deploy/grafana/dashboards /var/lib/grafana/dashboards/reflexr
