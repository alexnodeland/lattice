# stackr-db-init: the PostgreSQL client compose.yaml pins, with deploy/postgres/init.sql in it, for
# the AWS recipe's one-off task (RFC-0004, ADR-0034), which creates each service's role and
# database on RDS as db-init does on one machine. Built from lattice's root (deploy/build-images).
FROM postgres:17.11-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
LABEL org.opencontainers.image.source="https://github.com/alexnodeland/lattice"

COPY --link --chmod=a=rX packages/stackr/deploy/postgres/init.sql /init.sql
USER postgres
CMD ["psql", "--no-psqlrc", "--quiet", "--file=/init.sql"]
