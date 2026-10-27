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
#   VERIFY_DEPLOY=0                          (skip the post-push wait; default 1)
#   READBACK=0                               (skip the per-feature readback; default 1, exit 5 on fail)
#   AUTO_ROLLBACK=1 ... --auto-rollback-reason "<owner's reason for THIS deploy>"
#                                            (roll a P0 readback regression back to the
#                                             predecessor; default 0: the P0 is reported with
#                                             the exact command, exit 6, and nothing is pushed.
#                                             The reason must be given on each invocation; a
#                                             standing AUTO_ROLLBACK_REASON is refused. F-381,
#                                             review F-3 and cbd4ff1 N-4)
#   DEPLOY_VERIFY_TIMEOUT=900 DEPLOY_VERIFY_INTERVAL=15   (seconds)
#
# RELENG (2026-10-11): after pushing, ops/verify_deploy.py polls production /health until
# build.commit is the pushed sha. A push that the host never turns into a deployment (the
# 0417f35 push at 13:34Z did exactly that) now ends in exit 3 with a NO DEPLOY message instead
# of a silent success. Exit 4 = production never answered with a commit. The branch is NOT
# rewound on 3/4: the commit passed the guard; the host has to be made to deploy it.
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
auto_reason=""
while [ $# -gt 0 ]; do
  case "$1" in
    --deployed) deployed=${2:-}; shift 2 ;;
    --rollback-to) rollback_to=${2:-}; shift 2 ;;
    --reason) reason=${2:-}; shift 2 ;;
    --auto-rollback-reason) auto_reason=${2:-}; shift 2 ;;
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
# W4-ROLLBACK (F-381): a forward deploy must leave an executable way back. Rehearse the
# rollback from the candidate to the commit production runs now (built locally, never pushed,
# checked like a real rollback: the deployed sha must be in the candidate's DEPLOYED_HISTORY).
if [ -z "$rollback_to" ]; then
  if ! python3 "$top/ops/deploy_guard.py" rehearse-rollback --candidate "$candidate" \
        --deployed "$deployed" --repo "$top"; then
    echo "deploy.sh: no executable rollback from $candidate to $deployed (append it to brambleloop/release/DEPLOYED_HISTORY.json); nothing pushed to $branch" >&2
    exit 1
  fi
fi
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "deploy.sh: ALLOW $candidate (dry run; nothing pushed)"
  exit 0
fi
# The pre-push hook (if installed) checks the same push again; that is deliberate.
sha=$(git -C "$top" rev-parse "$candidate^{commit}")
git -C "$top" push "$remote" "$sha:refs/heads/$branch"
if [ "${VERIFY_DEPLOY:-1}" = "0" ]; then
  echo "deploy.sh: pushed $sha; VERIFY_DEPLOY=0, production NOT checked" >&2
  exit 0
fi
echo "deploy.sh: pushed $sha; waiting for production /health to report it" >&2
rc=0
python3 "$top/ops/verify_deploy.py" "$sha" || rc=$?
if [ "$rc" -ne 0 ]; then
  echo "deploy.sh: pushed $sha but production is NOT running it (verify_deploy exit $rc)" >&2
  exit "$rc"
fi
# W4-SMOKE (F-144): per-feature production readback. A deploy whose features do not read back
# is not done: exit 5 names them (the commit stays deployed; fix forward or roll back per
# ops/ROLLBACK_RUNBOOK.md). READBACK=0 skips it and says so.
if [ "${READBACK:-1}" = "0" ]; then
  echo "deploy.sh: DEPLOYED $sha; READBACK=0, features NOT read back" >&2
  exit 0
fi
if [ ! -f "$top/ops/readback.py" ]; then
  echo "deploy.sh: DEPLOYED $sha; ops/readback.py is absent from this checkout, features NOT read back" >&2
  echo "deploy.sh: DEPLOYED $sha"
  exit 0
fi
rb=0
# The readback is evidence: it is written where the completion board reads it (F-144), so a
# row whose feature did not read back on the deployed commit cannot be counted complete. The
# same file feeds the F-381 rollback decision below.
rb_json="${READBACK_JSON:-$top/brambleloop/research/final_build/w4/evidence_BOARD/prod_readback_$(printf %.12s "$sha")_$(date -u +%Y%m%dT%H%MZ).json}"
mkdir -p "$(dirname "$rb_json")"
python3 "$top/ops/readback.py" --sha "$sha" --json "$rb_json" || rb=$?
echo "deploy.sh: readback evidence $rb_json"
rb_out="$rb_json"   # the F-381 rollback decision below reads the same evidence
if [ "$rb" -ne 0 ]; then
  echo "deploy.sh: DEPLOYED $sha but the production readback did not pass (readback exit $rb)" >&2
  # W4-FMBATCH1 (F-381): the failure's severity decides containment. A P0 regression (safety,
  # spend ceilings, the runtime itself, or production unreachable) is rolled back to the commit
  # production ran before this push -- the rollback rehearsed above -- through the same guarded
  # path only when the owner turned it on (AUTO_ROLLBACK=1 + --auto-rollback-reason); a P1 is fixed
  # forward. By default the P0 decision is reported with the exact command and nothing is pushed.
  dec=0
  python3 "$top/ops/rollback_decision.py" --readback "$rb_out" --previous "$deployed" || dec=$?
  if [ "$dec" -eq 6 ] && [ -z "$rollback_to" ]; then
    # Review F-3: one re-read after a short delay, so a cold start that is briefly
    # unreachable is not read as a P0 regression.
    sleep "${READBACK_RETRY_S:-30}"
    rb=0
    python3 "$top/ops/readback.py" --sha "$sha" --json "$rb_out" || rb=$?
    dec=0
    if [ "$rb" -ne 0 ]; then
      python3 "$top/ops/rollback_decision.py" --readback "$rb_out" --previous "$deployed" || dec=$?
    else
      echo "deploy.sh: DEPLOYED $sha (readback PASS on re-read)"
      exit 0
    fi
  fi
  if [ "$dec" -eq 6 ]; then
    if [ -n "$rollback_to" ]; then
      echo "deploy.sh: P0 regression on the rollback $sha itself; NOT rolling back again (exit 6)" >&2
      exit 6
    fi
    # Review F-3: automatic production rollback is a push to production. It is OFF unless
    # AUTO_ROLLBACK=1, and even then it carries only a reason the owner wrote
    # (--auto-rollback-reason, given for this deploy) -- this
    # script never writes an "owner reason" itself.
    # Review cbd4ff1 N-4: the owner's reason is given on THIS invocation
    # (--auto-rollback-reason); a standing AUTO_ROLLBACK_REASON in the environment would
    # authorise every future rollback with one old sentence, so it is refused.
    if [ "${AUTO_ROLLBACK:-0}" != "1" ] || [ -z "$deployed" ] || [ -z "$auto_reason" ]; then
      if [ -n "${AUTO_ROLLBACK_REASON:-}" ] && [ -z "$auto_reason" ]; then
        echo "deploy.sh: AUTO_ROLLBACK_REASON in the environment is ignored: give the reason for this deploy with --auto-rollback-reason" >&2
      fi
      echo "deploy.sh: P0 regression on $sha: roll back with ops/deploy.sh --rollback-to $deployed --reason \"<your reason>\" (automatic rollback is off unless AUTO_ROLLBACK=1 with --auto-rollback-reason on this invocation; exit 6)" >&2
      exit 6
    fi
    echo "deploy.sh: P0 regression on $sha: rolling back to $deployed (AUTO_ROLLBACK=1)" >&2
    exec "$top/ops/deploy.sh" --rollback-to "$deployed" \
      --reason "$auto_reason" --deployed "$sha"
  fi
  exit 5
fi
echo "deploy.sh: DEPLOYED $sha (readback PASS)"
