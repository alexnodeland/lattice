#!/bin/sh
# The fallback: smokescreen, resolving through the flipping DNS server, plain HTTP and CONNECT.
T=${T:?}
run=$(date +%s)
s() { docker exec "spike0943-$T-client" curl -s -m 5 -x http://198.18.94.4:4750 "$@"; }
echo "== plain HTTP, fresh rebind.test names"
for i in 1 2 3 4; do
  name="s$i-$run.rebind.test"
  printf '%s -> %s\n' "$name" "$(s "http://$name/" -w ' [HTTP %{http_code}]' | tr -d '\n')"
done
echo "== CONNECT, fresh rebind.test names"
for i in 1 2 3 4; do
  name="p$i-$run.rebind.test"
  printf '%s -> %s\n' "$name" "$(s -p "http://$name/" -w ' [HTTP %{http_code}, CONNECT %{http_connect}]' | tr -d '\n')"
done
echo "== private.test"
s http://private.test/ -w ' [HTTP %{http_code}]\n'
sleep 1
echo "== the DNS server's log for this run"
docker logs "spike0943-$T-dns" 2>&1 | grep "$run"
echo "== smokescreen's log for this run"
docker logs "spike0943-$T-smokescreen" 2>&1 | grep "$run" | cut -c1-400
echo "== flipped before smokescreen asks: a first lookup (an earlier check) takes the public answer"
for i in 1 2; do
  name="f$i-$run.rebind.test"
  docker exec -w /egress "spike0943-$T-authz" python -c \
    "from servers import resolve; print('earlier check got', resolve('$name'))"
  printf '%s -> %s\n' "$name" "$(s "http://$name/" -w ' [HTTP %{http_code}]' | tr -d '\n')"
  printf '%s (CONNECT) -> %s\n' "$name" "$(s -p "http://$name/" -w ' [HTTP %{http_code}, CONNECT %{http_connect}]' | tr -d '\n')"
done
sleep 1
docker logs "spike0943-$T-dns" 2>&1 | grep "f[12]-$run"
