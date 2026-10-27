# Restart checkpoint: 2026-10-27T21:20Z (Opus weekly allowance at 98%)

All Opus workers were stopped to preserve the allowance. Their work is pushed as checkpoints. Commits named "WIP checkpoint" have tests that are NOT confirmed for that exact state.

## Production

- Production: `claude/repository-setup-nc9x6o` = **ee35a493**, deployed 2026-10-27T16:06Z.
- Readback: 11/12. The failing check is `no_unexpected_dead_letters_in_24h`.
- SHADOW mode, nothing published, Laura switches OFF.

## Branch heads and state

| Branch | Head | State | Next action |
|---|---|---|---|
| claude/w4-INTEG8-next | ca5ac1df | Batch 4 base: owner-queue race fix d11d494c, readback operator rows, DEPLOYED_HISTORY | merge reviewed branches below, then run the touched set once, then ONE full uninterrupted suite |
| claude/w4-READBACK | 5d95c4d0 | done; all listed suites pass | independent review running: claude/w4-SECREVIEW-READBACK-5d95c4d |
| claude/w4-LAUNCHFIX | 323f302b (WIP) | review of 0f0306dd said DO NOT SHIP: F-1 High (ops-token baseline), F-2/F-3 (D1 evidence unsealed, no age bound), F-6 (fee terms not bound), F-7 (photo vs render); owner clarification: photo gate on activation only | finish the fixes, run suites through testslot.sh, send a delta review |
| claude/w4-BRANDSCREEN | 24c5c90c | trademark knock-out screening | read the result |
| claude/w4-PHYSFIX | 74487340 | intake fixes | verify the tests, then review |
| claude/w4-PHYSFIX-PHOTO | f2a6ea29 | photo-first gallery ordering (on LAUNCHFIX) | verify, then review |
| claude/w4-ADOPT | c718b9a7 (WIP) | adoption done at 45a2d02c; follow-up (owner baseline, published_manually readers) partial | finish, then review |
| claude/w4-RESUMEFIX | adb7c77c (WIP) | F1–F8 in progress. MUST land before Batch 4 certifies (C1 is a live hole) | finish, run the probe, then a fresh independent review |
| claude/w4-PDF1 | 4ed0957a (WIP) | premium PDFs, layout fixes in progress | finish, visual QA, independent PDF and pattern audit, show the owner |
| claude/w4-LISTING1 | 565475dc (WIP) | basket identity source fix (kitchen and home, small only) in progress | finish, report whether the release hash changed |
| claude/w5-CONCEPT | af5cc7c1 (WIP) | research-to-concept intake, seed-shop watchlist | finish (Batch 5) |
| claude/w5-INVENTORY | 0066c708 (WIP) | 15-state inventory and dashboard; test count fix pending | finish (Batch 5) |
| claude/w4-LEDGER9 | 17d86da2 | six-state ledger | done |

## Owner decisions recorded this session (verbatim in ROSTER; record in DECISION_LOG when the branches merge)

- Basket = kitchen and home, small size only.
- Resumed runs never certify until the fixes, the probes and a fresh review all pass.
- The sample photo gates public publication only.
- The seed shops are monitored permanently.

## Owner actions pending

- Rotate BRAMBLELOOP_OPS_TOKEN, then ANTHROPIC_API_KEY.
- Apply the db-backup staged patch 616577eb (OFFLOAD_* removal).
- Approve deleting the partial dump 20261027T162700Z.
- Basket sample approval (when the kit is ready).
- Etsy AI-instructions ruling.
- Policy readings (via the #/policy form once deployed).
- Set BRAMBLELOOP_READBACK_TOKEN (once deployed).

## Resume commands

- Test gate: `/home/user/bl-runs/testslot.sh env PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 /home/user/bl-runs/venv-integ4/bin/python tests/<f>` (3 slots).
- Full suite (one at a time): `PY=/home/user/bl-runs/venv-integ4/bin/python REQUIRE_CLEAN=1 JOBS=3 setsid nohup bash run_tests.sh > /home/user/bl-runs/fullsuite-<sha>.out 2>&1 < /dev/null &`, from a frozen worktree.
- Deploy only after owner approval of the exact SHA: `DRY_RUN=1 sh ops/deploy.sh --deployed ee35a493dfd817bd105455091af601a3aa86eb9c` first.
