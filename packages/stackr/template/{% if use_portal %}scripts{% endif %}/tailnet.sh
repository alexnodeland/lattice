#!/usr/bin/env bash
# Serves the application on this machine's tailnet name, over HTTPS, for the tailnet only, with
# `tailscale serve`; never `tailscale funnel`, which would put it on the internet. Its ports stay
# on 127.0.0.1, where Tailscale reaches them. `make tailnet` and `make tailnet-off` run it.
#
# The portal is served on PORT, and mini apps' origin and each running editor on their own ports
# beside it, each the same port on the tailnet name as on 127.0.0.1 (portalr ADR-0084): a browser
# compares origins by host and port, so each keeps an origin of its own there too. `on` writes one
# key to DOTENV, PORTAL_EXTRA_URLS=https://<name>[:PORT], which tells the application the portal
# is reached there as well; `off` removes it. Either takes effect at the next `make up`. `off`
# removes the ports it is given, so give it the same PORT and SIBLING_PORTs as `on`.
#
# Usage: scripts/tailnet.sh on|off PORT APP_URL [SIBLING_PORT...]
#   PORT          the portal's HTTPS port on the tailnet name (443 serves at https://<name>/)
#   APP_URL       the application, as this machine reaches it, such as http://127.0.0.1:8800
#   SIBLING_PORT  a port served on 127.0.0.1 beside it, such as mini apps' 8801 or an editor's
#
# It is all or nothing: it changes no port until every one is free or already its own, refuses
# one something else is served on (a site or a TCP forward) and, for `on`, one Funnel puts on the
# internet; and if serving one fails it removes those this run added, and no other. `off` removes
# only what serves this application, Funnel with it. Port 8443 is never in its plan. TAILSCALE
# names the CLI where it isn't on the PATH, UV the uv that runs its Python, and DOTENV the file
# it writes the key to, .env by default.

set -euo pipefail

usage="usage: tailnet.sh on|off PORT APP_URL [SIBLING_PORT...]"
action=${1:?$usage}
port=${2:?$usage}
app=${3:?$usage}
shift 3
siblings=("$@")
env_file=${DOTENV:-.env}

case $action in
  on | off) ;;
  *)
    echo "$usage" >&2
    exit 2
    ;;
esac

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

python() { "${UV:-uv}" run --no-project python -c "$@"; }

# This machine's tailnet name, from `status --json --peers=false` (stdin): only once Tailscale is
# signed in and running, with MagicDNS giving it a name, and checked before it reaches serve or
# the env file.
NAME='
import json, re, sys
try:
    me = json.loads(sys.stdin.read() or "{}") or {}
except ValueError:
    me = {}
name = str((me.get("Self") or {}).get("DNSName") or "").rstrip(".").lower()
if me.get("BackendState") != "Running" or not name:
    sys.exit("tailnet: Tailscale is not signed in / MagicDNS is off; sign in, turn MagicDNS on, and run this again")
if not re.fullmatch(r"[a-z0-9.-]+", name):
    sys.exit(f"tailnet: the tailnet name of this machine, {name!r}, is not a host name")
print(name)
'

# The plan, checked before anything changes, from what the tailnet name serves now (stdin): the
# origin the portal is reached at, then a line for each port to change, `<port> <target>`; or
# why nothing changes, and a failure.
PLAN='
import json, os, re, sys
action, env_file, name, port, app, *siblings = sys.argv[1:]
served = json.loads(sys.stdin.read() or "{}") or {}
plan = {port: app, **{each: f"http://127.0.0.1:{each}" for each in siblings}}
for each in plan:
    if not re.fullmatch(r"[1-9][0-9]{0,4}", each) or int(each) > 65535:
        sys.exit(f"tailnet: {each} is not a port")
if len(plan) != 1 + len(siblings):
    sys.exit("tailnet: a port is named twice")
if "8443" in plan:
    sys.exit("tailnet: port 8443 is left to what serves it there; choose another, such as 8444")
origin = f"https://{name}" if port == "443" else f"https://{name}:{port}"

def state(each, target):
    """free, ours, funnel (ours, with Funnel on) or taken."""
    def here(section):
        return [v for k, v in (served.get(section) or {}).items() if k.endswith(f":{each}")]
    funnel = any(here("AllowFunnel"))
    if each not in (served.get("TCP") or {}) and not funnel:
        return "free"
    if [site.get("Handlers") or {} for site in here("Web")] != [{"/": {"Proxy": target}}]:
        return "taken"
    return "funnel" if funnel else "ours"

states = {each: state(each, target) for each, target in plan.items()}
taken = ", ".join(each for each, now in states.items() if now == "taken")
public = ", ".join(each for each, now in states.items() if now == "funnel")
if taken or (public and action == "on"):
    why = f"something else is served on port {taken}" if taken else f"Funnel puts port {public} on the internet"
    sys.exit(
        f"tailnet: nothing changed: {why};\n"
        "  choose another, such as TAILNET_PORT=8444, or run make tailnet-off first"
    )
if action == "on":
    if not os.path.isfile(env_file):
        sys.exit(f"tailnet: nothing changed: there is no {env_file}; run make env first")
    if not os.access(env_file, os.W_OK):
        sys.exit(f"tailnet: nothing changed: {env_file} cannot be written")
    with open(env_file, encoding="utf-8") as lines:
        named = [l.split("=", 1)[1].strip() for l in lines if l.startswith("PORTAL_EXTRA_URLS=")]
    if any(value not in ("", origin) for value in named):
        sys.exit(
            f"tailnet: nothing changed: {env_file} sets PORTAL_EXTRA_URLS to something else, which"
            " counts as set by hand, quoted or not;\n"
            f"  leave it empty for this to set, or add {origin} to it yourself"
        )
print(origin)
wanted = ("free",) if action == "on" else ("ours", "funnel")
for each, target in plan.items():
    if states[each] in wanted:
        print(each, target)
'

# The one key, in DOTENV as it is: `on` names the origin, `off` removes it where it names that
# origin and nothing else. It prints "changed" if it changed the file. Each line keeps its own
# ending, CRLF included.
KEY='
import sys
action, env_file, origin = sys.argv[1:]
key = "PORTAL_EXTRA_URLS="
try:
    with open(env_file, encoding="utf-8", newline="") as read:
        lines = read.read().splitlines(keepends=True)
except FileNotFoundError:
    sys.exit()
ours = [i for i, line in enumerate(lines) if line.startswith(key)]
if action == "on":
    if [lines[i].strip() for i in ours] == [key + origin]:
        sys.exit()
    kept = [line for i, line in enumerate(lines) if i not in ours[1:]]
    if ours:
        line = kept[ours[0]]
        ending = line[len(line.rstrip("\r\n")):] or "\n"
        kept[ours[0]] = key + origin + ending
    else:
        kept.append(("" if not kept or kept[-1].endswith("\n") else "\n") + f"{key}{origin}\n")
else:
    kept = [line for line in lines if line.strip() != key + origin]
    if len(kept) == len(lines):
        sys.exit()
# Written in place, deliberately, not replaced: the file keeps its inode and its mode (0600), as
# a bind mount of it needs.
with open(env_file, "r+", encoding="utf-8", newline="") as write:
    write.write("".join(kept))
    write.truncate()
print("changed")
'

name=$("$tailscale" status --json --peers=false </dev/null | python "$NAME")
plan=$("$tailscale" serve status --json </dev/null | python "$PLAN" \
  "$action" "$env_file" "$name" "$port" "$app" "${siblings[@]+"${siblings[@]}"}")
origin=$(head -n 1 <<<"$plan")
changes=()
while read -r line; do
  [[ -z $line ]] || changes+=("$line")
done < <(tail -n +2 <<<"$plan")

# tailscale's own output is shown: it says when this machine must first allow Serve or HTTPS.
# Each call's stdin is /dev/null, so none reads what is meant for another.
added=()
changed_ports=()
for change in "${changes[@]+"${changes[@]}"}"; do
  each=${change%% *}
  target=${change#* }
  if [[ $action == on ]]; then
    if ! "$tailscale" serve --bg --yes --https="$each" "$target" </dev/null; then
      for done in "${added[@]+"${added[@]}"}"; do
        "$tailscale" serve --yes --https="$done" off </dev/null || true
      done
      echo "tailnet: port $each wasn't served, so those this run added are removed again" >&2
      exit 1
    fi
    added+=("$each")
  elif ! "$tailscale" serve --yes --https="$each" off </dev/null; then
    removed="${changed_ports[*]+"${changed_ports[*]}"}"
    echo "tailnet: port $each wasn't removed (removed so far: ${removed:-none}); $env_file is unchanged" >&2
    exit 1
  fi
  changed_ports+=("$each")
done

changed=$(python "$KEY" "$action" "$env_file" "$origin")
if [[ $action == on ]]; then
  echo "On your tailnet only: $origin/portalr/app/ and $origin/portalr/admin/"
  if ((${#siblings[@]})); then
    beside="${siblings[*]}"
    echo "  with mini apps and the editors beside it, on ports ${beside// /, }"
  else
    echo "tailnet: no mini apps' or editors' port beside it: set PORTAL_APPS_URL, and pass FILES" \
      "to make tailnet unless .env sets FILES_CRAFTS" >&2
  fi
  [[ -z $changed ]] || echo "$env_file now sets PORTAL_EXTRA_URLS=$origin: run \`make up\` to apply"
else
  if ((${#changed_ports[@]})); then
    removed="${changed_ports[*]}"
    echo "No longer served on your tailnet or by Funnel: port ${removed// /, }"
  else
    echo "Nothing of this application's is served on your tailnet"
  fi
  [[ -z $changed ]] || echo "$env_file no longer sets PORTAL_EXTRA_URLS: run \`make up\` to apply"
fi
