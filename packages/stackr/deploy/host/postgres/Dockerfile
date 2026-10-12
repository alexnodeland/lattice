# PostgreSQL with pgBackRest, for a single host (RFC-0004): the image compose.yaml pins, which
# scripts/check-config holds this one to, with Alpine's pgbackrest package.
FROM postgres:17.11-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24

RUN apk add --no-cache pgbackrest
COPY pgbackrest-conf stackr-entrypoint /usr/local/bin/

ENTRYPOINT ["stackr-entrypoint"]
CMD ["postgres"]
