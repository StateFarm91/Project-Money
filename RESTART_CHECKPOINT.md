# Restart checkpoint, 2026-10-31T06:50Z

**Read this first after any interruption** (usage limit, worker restart or new session). Then read `COORDINATION.json` and `BRANCH_OWNERSHIP.md`. Commits named "WIP checkpoint" have tests that are NOT confirmed for that exact state.

## Production
- Production is `claude/repository-setup-nc9x6o` at **ee35a493**, deployed 2026-10-27T16:06Z.
- `/api/verify` returned ok=True, 13/13, at 2026-10-31T06:45Z.
- Phase SHADOW. Nothing is published; Laura's switches are OFF.

## Batch 4: `claude/w4-INTEG8-next` at 98904d86
**Merged:**
- READBACK 5d95c4d0, with review findings L1–L4 fixed in bcbe391b.
- LAUNCHFIX 8c14dbf2, SHIP. Recommended follow-up: N-2, seal the owner photo attestation.
- RESUMEFIX e634e6fc, SHIP for Batch 4. A resumed run never certifies.
- LISTING1 d11fe80f, SHIP. Low findings F-1 to F-3 can be fixed at integration.
- The final-segment declaration (282e47ce).

**Post-merge suites:** running into `scratchpad/b4_listing.out`. `test_w4_resume_runner` P09 failed once under heavy load and then passed on a clean rerun; watch it in the full suite.

**Still to merge before certification:**

| Branch | Head | State |
|---|---|---|
| claude/w4-PHYSFIX | 626afdf8 | fixing review F1–F7 (F1 and F2 are High); worker resumed |
| claude/w4-PHYSFIX-PHOTO | 78888e44 (WIP) | built on LAUNCHFIX; readiness text; worker resumed |
| claude/w4-ADOPT | f4104a47 (WIP) | fixing review F-1 to F-4 (F-1 is High); worker resumed |

**Then:** merge these three, run the touched suites once, run ONE uninterrupted full suite (only with enough capacity to finish it), then the deploy guard, DRY_RUN, rollback rehearsal and the owner's exact-SHA approval. Never deploy without that approval.

**Merge reconciliation note:** ADOPT and READBACK both edit `app/main.py` (api_catalogue) and `app/verify_checks.py`.

## Batch 5
| Branch | Head | State |
|---|---|---|
| claude/w5-INVENTORY | 5e72bce8 | fixing review H1, M1–M4 and mutants M7, M9, M12; worker resumed |
| claude/w5-CONCEPT | 933bf742 | done; review running, writing to claude/w5-SECREVIEW-CONCEPT-933bf74 |
| claude/w4-PDF1 | 63d9ceec | coaster and basket editions done |

**PDF1 audits:**
- Coaster: FIX BEFORE SALE, F1–F4 Medium, to be fixed in a 1.2.1 pass.
- Basket: audit running, writing to claude/w4-PDFAUDIT-basket-63d9cee. Batch the 1.2.1 fixes after it reports.

**opus2/p0-revenue-workforce:**

| Commit | Content | Verdict |
|---|---|---|
| 54766c9e | size gate, laura_home | CHANGES_REQUIRED (review A) |
| 54766c9e | rim negative, p0_acceptance | ACCEPT |
| 54766c9e | chain successors, scan evidence, lessons | review B running (claude/w5-SECREVIEW-OPUS2B-54766c9) |
| dd211ff4 | photo-led gallery certificate | to review after B |

**Integrator-planned work:**
- Automatic premium PDF inside `assets.build`.
- The listing-package assembly job.

## Owner directives in force
- **D-W5-OWNER-RETURN-TO-PLAN (permanent):** no Etsy AI-pattern policy research or compliance engineering. Existing safeguards stay. Never misrepresent authorship, testing or provenance.
- Opus 5.5 Medium only. Keep SHADOW. CA$100 ceiling. Laura's identity is locked.

## Owner actions pending
- Rotate BRAMBLELOOP_OPS_TOKEN, then ANTHROPIC_API_KEY.
- Apply the db-backup staged patch 616577eb.
- Approve deleting the partial dump 20261027T162700Z.
- Basket tester kit (about CA$66): ready once its TEST.pdf is rebuilt from the corrected source after PHYSFIX merges.

## Resume commands
- Test gate, run from `brambleloop/`: `/home/user/bl-runs/testslot.sh env PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 /home/user/bl-runs/venv-integ4/bin/python tests/<f>`.
- Full suite: `PY=/home/user/bl-runs/venv-integ4/bin/python REQUIRE_CLEAN=1 JOBS=3 setsid nohup bash run_tests.sh`. Run it only when nothing else is running, and only with enough usage left to finish.
