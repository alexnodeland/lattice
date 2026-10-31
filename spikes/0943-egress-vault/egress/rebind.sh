#!/bin/sh
# Question 1: through each listener, fresh names under rebind.test, whose answers flip per
# query between 198.18.94.20 (allowed) and 127.0.0.1 (refused, where the decoy listens in
# Envoy's own namespace). Then a caller that sends x-lattice-upstream itself.
T=${T:?}
run=$(date +%s)
c() { l=$1; shift; docker exec "spike0943-$T-client" curl -s -m 5 -x "http://198.18.94.2:$l" \
  --proxy-header 'Proxy-Authorization: Bearer tok-sandbox-a' "$@"; }
for listener in 10000 10001 10003; do
  echo "== listener $listener"
  for i in 1 2 3 4 5; do
    name="r$i-$listener-$run.rebind.test"
    printf '%s -> %s' "$name" "$(c "$listener" "http://$name/" | tr -d '\n')"
    echo
  done
done
echo "== caller-supplied x-lattice-upstream: 127.0.0.1:80 (and -ip), to an allowed host"
for listener in 10000 10003; do
  printf 'listener %s -> %s\n' "$listener" "$(c "$listener" -H 'x-lattice-upstream: 127.0.0.1:80' \
    -H 'x-lattice-upstream-ip: 127.0.0.1' http://public.test/ | tr -d '\n')"
done
sleep 2
echo "== the DNS server's log for this run (who asked, what it got)"
docker logs "spike0943-$T-dns" 2>&1 | grep "$run"
echo "== Envoy's access log for this run"
docker logs "spike0943-$T-envoy" 2>&1 | grep '^{' | grep -E "$run|public.test" | tail -18
