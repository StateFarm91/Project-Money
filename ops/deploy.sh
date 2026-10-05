#!/bin/sh
# The one sanctioned production deploy (F-461). A push to the production branch IS the deploy
# (Railway builds it), so this script runs ops/deploy_guard.py `check` on HEAD against the
# commit production reports and pushes only on ALLOW. On REFUSE it pushes nothing and exits 1.
#
#   ops/deploy.sh [--deployed <sha>]   (else BRAMBLELOOP_DEPLOYED_SHA, else ops/deployed_sha.py)
#   DRY_RUN=1 ops/deploy.sh ...             (check only; never pushes)
#   REMOTE=origin (default)
set -eu
top=$(git rev-parse --show-toplevel)
remote=${REMOTE:-origin}
branch=claude/repository-setup-nc9x6o
deployed=""
if [ "${1:-}" = "--deployed" ]; then deployed=${2:-}; fi
if [ -z "$deployed" ]; then
  deployed=${BRAMBLELOOP_DEPLOYED_SHA:-}
fi
if [ -z "$deployed" ]; then
  # Production's own answer; unknown stays empty and the guard refuses on it.
  deployed=$(python3 "$top/ops/deployed_sha.py") || deployed=""
fi
if ! python3 "$top/ops/deploy_guard.py" check --candidate HEAD --repo "$top" \
      --records "$top/brambleloop/artifacts/suite_runs" --deployed "$deployed"; then
  echo "deploy.sh: deploy_guard REFUSED; nothing pushed to $branch" >&2
  exit 1
fi
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "deploy.sh: ALLOW (dry run; nothing pushed)"
  exit 0
fi
# The pre-push hook (if installed) checks the same push again; that is deliberate.
git -C "$top" push "$remote" "HEAD:refs/heads/$branch"
