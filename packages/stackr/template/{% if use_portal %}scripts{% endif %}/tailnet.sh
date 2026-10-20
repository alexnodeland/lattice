#!/usr/bin/env bash
# Serves the application on this machine's tailnet name, over HTTPS, for the tailnet only, with
# `tailscale serve`; never `tailscale funnel`, which would put it on the internet. Its port stays
# on 127.0.0.1, where Tailscale reaches it. The portal signs in on the application's own origin
# (PORTAL_SUPABASE_URL=/), so it needs nothing else served. `make tailnet` and `make tailnet-off`
# run it.
#
# Usage: scripts/tailnet.sh on|off PORT APP_URL
#   PORT      the HTTPS port on the tailnet name (443 serves at https://<name>/)
#   APP_URL   the application, as this machine reaches it, such as http://127.0.0.1:8800
#
# It changes PORT alone: `on` refuses a port something else is served on, and `off` one it didn't
# set up. TAILSCALE names the CLI where it isn't on the PATH, and UV the uv that reads its JSON.

set -euo pipefail

usage="usage: tailnet.sh on|off PORT APP_URL"
action=${1:?$usage}
port=${2:?$usage}
app=${3:?$usage}

# The CLI: on the PATH, or inside the macOS app, which puts none there.
tailscale=${TAILSCALE:-$(command -v tailscale || true)}
mac=/Applications/Tailscale.app/Contents/MacOS/Tailscale
if [[ -z $tailscale && -x $mac ]]; then
  tailscale=$mac
fi
if [[ -z $tailscale ]]; then
  echo "tailnet: no tailscale CLI; install Tailscale (https://tailscale.com/download), sign in," >&2
  echo "  and run this again, or set TAILSCALE to the CLI's path" >&2
  exit 1
fi

json() { "${UV:-uv}" run --no-project python -c "$@"; }

# What PORT serves now: nothing ("free"), the application alone ("ours"), or more ("taken"). A
# port Funnel puts on the internet is taken, whatever it serves: `on` would leave it there.
state=$("$tailscale" serve status --json | json '
import json, sys
port, app = sys.argv[1:]
config = json.loads(sys.stdin.read() or "{}") or {}
def here(section):
    return [v for k, v in (config.get(section) or {}).items() if k.endswith(f":{port}")]
handlers = [site.get("Handlers") or {} for site in here("Web")]
if any(here("AllowFunnel")):
    print("taken")
elif port not in (config.get("TCP") or {}):
    print("free")
else:
    print("ours" if handlers == [{"/": {"Proxy": app}}] else "taken")
' "$port" "$app")
if [[ $state == taken ]]; then
  echo "tailnet: something else is served on port $port, or Funnel puts it on the internet;" >&2
  echo "  choose another, such as TAILNET_PORT=8444" >&2
  exit 1
fi

case $action in
  on)
    "$tailscale" serve --bg --yes --https="$port" "$app" >/dev/null
    name=$("$tailscale" status --json | json \
      'import json, sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
    origin=https://$name
    [[ $port == 443 ]] || origin=$origin:$port
    echo "On your tailnet only: $origin/portalr/app/ and $origin/portalr/admin/"
    ;;
  off)
    if [[ $state == ours ]]; then
      "$tailscale" serve --yes --https="$port" off >/dev/null
      echo "No longer on your tailnet, on port $port"
    else
      echo "Nothing of this application's is served on port $port"
    fi
    ;;
  *)
    echo "$usage" >&2
    exit 2
    ;;
esac
