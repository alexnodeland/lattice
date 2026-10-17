# shellcheck shell=bash
# Sourced by the scripts that run a compose project of their own (scripts/api, scripts/image,
# portalr's and the client's `api`, and the web packages' `bdd`), so each run names it the same
# way.
#
# A fixed name would be shared by every run at once, in other worktrees, say, and the one that
# stopped would take the others' containers and volumes with it. So a run's project is named with
# a token of its own, and the only thing it ever removes, in its EXIT trap, is that project.
#
#   project=$(unique_project portalr-bdd)   # portalr-bdd-3f9a1c0e

# It fails, and prints nothing, if there is no token to be had, so a script that assigns its result
# stops there and never falls back to a name that other runs share.
unique_project() {
  local token
  token=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')
  [[ -n $token ]] || { echo "unique_project: no random token" >&2; return 1; }
  printf '%s-%s' "${1:?usage: unique_project NAME}" "$token"
}
