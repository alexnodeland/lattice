#!/bin/sh
# A throwaway CA and a certificate for api.upstream.test, made at run time, never committed.
set -eu
d=$(dirname "$0")/certs
mkdir -p "$d"
cd "$d"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 2 \
  -subj /CN=spike0943-ca -keyout ca.key -out ca.crt 2>/dev/null
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj /CN=api.upstream.test \
  -keyout upstream.key -out upstream.csr 2>/dev/null
printf 'subjectAltName=DNS:api.upstream.test\n' > san.ext
openssl x509 -req -in upstream.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 2 \
  -extfile san.ext -out upstream.crt 2>/dev/null
chmod 644 ./*
echo "certs in $d"
