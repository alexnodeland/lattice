#!/bin/sh
# Question 2: a plain-HTTP forward-proxy request to listener 10002; Envoy originates TLS to
# api.upstream.test (SNI and SAN from Host, CA the spike's), the authorizer injects the
# credential, and every credential header the caller sent is stripped.
T=${T:?}
c() { docker exec "spike0943-$T-client" curl -s -m 5 -x http://198.18.94.2:10002 "$@"; }
echo "== caller sends X-Lattice-Secret and its own Authorization and x-api-key"
c -i --proxy-header 'Proxy-Authorization: Bearer tok-litellm-a' \
  -H 'X-Lattice-Secret: sec_0123456789abcdef' -H 'Authorization: Bearer caller-own' \
  -H 'x-api-key: caller-key' http://api.upstream.test/v1/models
echo "== an unknown reference"
c --proxy-header 'Proxy-Authorization: Bearer tok-litellm-a' \
  -H 'X-Lattice-Secret: sec_ffffffffffffffff' http://api.upstream.test/v1/models
echo "== no credential: the caller's Authorization is stripped, nothing replaces it"
c --proxy-header 'Proxy-Authorization: Bearer tok-litellm-a' -H 'Authorization: Bearer caller-own' \
  http://api.upstream.test/v1/models
sleep 1
echo "== Envoy's access log"
docker logs "spike0943-$T-envoy" 2>&1 | grep '^{' | grep '"listener":10002' | tail -3
echo "== the authorizer down: every listener refuses"
docker stop "spike0943-$T-authz" >/dev/null
for l in 10000 10001 10002 10003; do
  printf 'listener %s -> HTTP %s\n' "$l" "$(docker exec "spike0943-$T-client" curl -s -o /dev/null \
    -w '%{http_code}' -m 5 -x "http://198.18.94.2:$l" \
    --proxy-header 'Proxy-Authorization: Bearer tok-sandbox-a' http://public.test/)"
done
docker start "spike0943-$T-authz" >/dev/null
sleep 1
docker logs "spike0943-$T-envoy" 2>&1 | grep '^{' | grep '"code":403' | tail -4
