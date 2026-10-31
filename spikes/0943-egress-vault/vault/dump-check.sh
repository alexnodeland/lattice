#!/bin/sh
# Run inside the db container: dump the database and the cluster, and look for the root key,
# the plaintexts and the ciphertext rows in each.
set -eu
pg_dump -U supabase_admin -h localhost postgres > /tmp/dump.sql
pg_dumpall -U supabase_admin -h localhost > /tmp/dumpall.sql
K=$(cat /etc/postgresql-custom/pgsodium_root.key)
echo "root key: /etc/postgresql-custom/pgsodium_root.key, ${#K} hex chars; PGDATA is $PGDATA"
for f in /tmp/dump.sql /tmp/dumpall.sql; do
  echo "$f: key (any case) $(grep -ci "$K" "$f"), TOKEN-OF-TENANT-A $(grep -c TOKEN-OF-TENANT-A "$f"), KEY-OF-TENANT-B $(grep -c KEY-OF-TENANT-B "$f"), vault.secrets rows $(grep -c -E "^[0-9a-f-]{36}	sec_" "$f")"
done
echo "files under PGDATA containing the key: $(grep -rl "$K" "$PGDATA" 2>/dev/null | wc -l)"
grep -E "^[0-9a-f-]{36}	sec_" /tmp/dump.sql | cut -f2-4
