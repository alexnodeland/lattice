#!/bin/sh
# CONNECT through ORIGINAL_DST (listener 10004), and the upstream certificate's SAN checked
# when Envoy originates TLS (listener 10002).
T=${T:?}
run=$(date +%s)
A='Proxy-Authorization: Bearer tok-sandbox-a'
echo "== CONNECT tunnels to fresh rebind.test names, port 80"
for i in 1 2 3; do
  name="t$i-$run.rebind.test"
  printf '%s -> %s\n' "$name" "$(docker exec "spike0943-$T-client" curl -s -m 5 -p \
    -x http://198.18.94.2:10004 --proxy-header "$A" "http://$name/" | tr -d '\n')"
done
echo "== CONNECT to private.test"
docker exec "spike0943-$T-client" curl -s -m 5 -p -x http://198.18.94.2:10004 --proxy-header "$A" \
  http://private.test/ -o /dev/null -w 'HTTP %{http_code}, CONNECT answered %{http_connect}\n'
echo "== CONNECT, TLS end to end (Envoy sees nothing inside), to api.upstream.test:443"
docker exec "spike0943-$T-client" curl -s -m 5 -k -x http://198.18.94.2:10004 --proxy-header "$A" \
  https://api.upstream.test/ | head -3
echo "== listener 10002 to public.test: the certificate's SAN is api.upstream.test, not public.test"
docker exec "spike0943-$T-client" curl -s -m 5 -x http://198.18.94.2:10002 \
  --proxy-header 'Proxy-Authorization: Bearer tok-litellm-a' http://public.test/ -w ' HTTP %{http_code}\n'
sleep 1
docker logs "spike0943-$T-dns" 2>&1 | grep "$run"
echo "== the gRPC authorizer"
docker logs "spike0943-$T-grpc-authz" 2>&1 | grep "$run"
docker logs "spike0943-$T-envoy" 2>&1 | grep '^{' | grep -E "\"listener\":1000[24]" | tail -6
