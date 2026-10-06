#!/bin/sh
# The one sanctioned production deploy (F-461). A push to the production branch IS the deploy
# (the host builds it), so this script runs ops/deploy_guard.py `check` on the candidate against
# the commit production reports and pushes only on ALLOW. On REFUSE it pushes nothing, exit 1.
#
#   ops/deploy.sh [--deployed <sha>]   (else BRAMBLELOOP_DEPLOYED_SHA, else ops/deployed_sha.py)
#   ops/deploy.sh --rollback-to <sha> --reason "<owner's reason>" [--deployed <sha>]
#        A3-06: sanctioned rollback. Writes a commit on top of the deployed one carrying exactly
#        the tree of <sha>, which must be in brambleloop/release/DEPLOYED_HISTORY.json; the
#        guard checks it like any candidate (see ops/ROLLBACK_RUNBOOK.md).
#   DRY_RUN=1 ops/deploy.sh ...             (check only; never pushes)
#   REMOTE=origin (default)
#
# The candidate must carry a TRACKED release record (A3-05): `ops/deploy_guard.py record`
# after a clean full run, committed on top. Untracked suite records are not believed.
set -eu
top=$(git rev-parse --show-toplevel)
remote=${REMOTE:-origin}
branch=claude/repository-setup-nc9x6o
deployed=""
rollback_to=""
reason=""
while [ $# -gt 0 ]; do
  case "$1" in
    --deployed) deployed=${2:-}; shift 2 ;;
    --rollback-to) rollback_to=${2:-}; shift 2 ;;
    --reason) reason=${2:-}; shift 2 ;;
    *) echo "deploy.sh: unknown argument $1" >&2; exit 2 ;;
  esac
done
if [ -z "$deployed" ]; then
  deployed=${BRAMBLELOOP_DEPLOYED_SHA:-}
fi
if [ -z "$deployed" ]; then
  # Production's own answer; unknown stays empty and the guard refuses on it.
  deployed=$(python3 "$top/ops/deployed_sha.py") || deployed=""
fi
candidate=HEAD
if [ -n "$rollback_to" ]; then
  if ! candidate=$(python3 "$top/ops/deploy_guard.py" rollback-commit --to "$rollback_to" \
        --reason "$reason" --deployed "$deployed" --repo "$top"); then
    echo "deploy.sh: rollback REFUSED by deploy_guard; nothing pushed to $branch" >&2
    exit 1
  fi
fi
if ! python3 "$top/ops/deploy_guard.py" check --candidate "$candidate" --repo "$top" \
      --records "$top/brambleloop/artifacts/suite_runs" --deployed "$deployed"; then
  echo "deploy.sh: deploy_guard REFUSED; nothing pushed to $branch" >&2
  exit 1
fi
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "deploy.sh: ALLOW $candidate (dry run; nothing pushed)"
  exit 0
fi
# The pre-push hook (if installed) checks the same push again; that is deliberate.
git -C "$top" push "$remote" "$candidate:refs/heads/$branch"
