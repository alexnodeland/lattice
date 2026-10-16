# Sourced by the scripts that run a compose project of their own (scripts/api, portalr's and the
# client's `api`, and the web packages' `bdd`), so each run names it the same way.
#
# A fixed name would be shared by every run at once, in other worktrees, say, and the one that
# stopped would take the others' containers and volumes with it. So a run's project is named with
# a token of its own, and the only thing it ever removes, in its EXIT trap, is that project.
#
#   project=$(unique_project portalr-bdd)   # portalr-bdd-3f9a1c0e

unique_project() {
  printf '%s-%s' "${1:?usage: unique_project NAME}" "$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
}
