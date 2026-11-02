# OPUS2 engineering checkpoint (read first on every wake)

Updated: 2026-11-01T16:35Z. The engineering loop rewrites this file at the end of every work
unit and pushes it to `origin/opus2/checkpoint`. A container reset loses /tmp and the
worktrees, not this file.

## How a wake resumes
1. `git fetch origin`; read this file at `origin/opus2/checkpoint`.
2. Recreate missing worktrees: `git worktree add <path> <branch>`, and
   `pip install -r brambleloop/requirements.txt` if `import sqlalchemy` fails.
3. Read `COORDINATION.json` (`reviews`, `unowned`, `claims`) and `BRANCH_OWNERSHIP.md` on
   `origin/claude/w4-INTEG8-next`, and the newest comments on PRs #3, #5 and #6. The integrator
   comments under the same GitHub account, so its comments may not wake this session; poll them.
4. Take the first unfinished item in the queue below. Skip it if the "Done" log shows it pushed.
   Before starting an item, confirm that no other operator's claim covers it.
5. Work it: fix, focused tests, commit, push. Then update the PR, the handoff, this file and
   the claim.
6. Continue with the next item in the same turn while capacity lasts.

## Worktrees
- `/home/user/opus2-p0`: `opus2/p0-revenue-workforce` (PR #3; frozen except review fixes)
- `/home/user/opus2-pkg`: `opus2/p0-listing-package` (PR #5)
- `/home/user/opus2-race`: `opus2/p1-owner-queue-races` (PR #6)
- `/home/user/opus2-ckpt`: `opus2/checkpoint` (this file)

## Work queue (priority order)
1. EF2-6 MEDIUM (PR #6): restate the cost basis on merge; never lower a stated ceiling.
2. EF2-4 MEDIUM (PR #5): only an owner-closed row suppresses a new request. EF2-5: supersede the legacy key.
3. EF2-1 MEDIUM + EF2-2 (PR #3): `title_promise` counts finished objects, not assembled
   straps (the integrator asked for this); refuse tote second objects and features; pin the
   route with tests. EF2-3 and EF2-3b LOW follow-ups.
4. B-5 (PR #6): partial unique index plus an explicit duplicate-closing script. The integrator
   made it an integration blocker before production and Postgres.
5. EF2-7 and EF2-8 LOW (PR #6): an `owner_queue.ensure`-style helper returns the persistent row;
   a revert restores state history.
6. P1-CULTURE-SWEEP-TIMEOUT (unowned, production dead letter, 2026-11-01T07:05Z). Claim it
   first, on a fresh branch from `claude/w4-INTEG8-next`.
7. Construction breadth. The next item comes from handoff §30 or from the knowledge-gap counts;
   per-stitch colour needs Main Opus's decision, so propose it on PR #3.

## In flight (10:00Z)
- PR #6 `/home/user/opus2-race` (uncommitted): EF2-6, EF2-8 and B-5, 11/11. The 115-suite
  regression is running (`/tmp/claude-0/oq4_results.txt`); the handoff text is drafted in
  `/tmp/claude-0/oq_handoff_add.md`.
- PR #3 `/home/user/opus2-p0` (uncommitted): EF2-1/2/3/3b. The 104-suite regression is running
  (`/tmp/claude-0/ef2_results.txt`).
- `opus2/p0-cir-colourwork` `/home/user/opus2-colour` (uncommitted): `Op.color` through the
  model, compiler, twin, writer and reverse compiler; 6/6; no Launch-0 digest moves. The 84-suite
  regression is running (`/tmp/claude-0/cw2_results.txt`). The proposal is on PR #3; the
  integrator decides.
- `opus2/p0-family-membership` `/home/user/opus2-family` (uncommitted; claim in its
  COORDINATION): `family_of` reads the culture signal; culture next members; 2/2. Its suites are
  running (task output b383ivf3a).
- Next once these land:
  - a pet bed construction, after PR #3's EF2 push: a vessel with a large base and a low wall,
    routed by "pet bed", "cat bed" or "dog bed" titles in the `pet` category, with a measured
    size added to `products.vessels`;
  - the EF2-7 `owner_queue.ensure` helper;
  - mosaic vessel drafting via `Op.color`, after the integrator decides.
- Hats re-checked at 10:05Z: no published hat-height or ease standard was found (only a
  truncated designer PDF crediting a publisher's chart). They stay refused, and the gap stays
  with Codex reference intake.

- 10:30Z loop firing: Batch 4 is CERTIFIED (fa139a78, 10122 passing) and the base is now
  0967c3ee. PRs #5, #6, #7 and #8 merge cleanly into it. PR #3 conflicts in release_gates.py
  and withholding.py (REVERIFY-WITHHOLD vs PHYSFIX physical-size kind): both are union
  resolutions, prepared in the scratch worktree /tmp/claude-0/mt, with the tests running
  (task b91dvj03c). It goes on a separate branch, opus2/p0-revenue-workforce-b4merge, for
  the integrator; the frozen PR #3 head is not touched.

- 11:50Z in flight:
  - `opus2/p0-pet-bed` (/home/user/opus2-pet): the pet basket bed is 3/3; the 44-suite run is
    going (/tmp/claude-0/pet_results.txt).
  - `opus2/p0-stocking` (/home/user/opus2-stock): the two-panel stocking is 3/3; the 44-suite
    run is going (/tmp/claude-0/st_results.txt).
  - PR #9: the colour_changes tapestry follow-up is uncommitted; its 37-suite run is going
    (/tmp/claude-0/cc_results.txt).
  - Both new branches are stacked on opus2/p0-revenue-workforce-b4merge.

- 12:30Z loop: no new reviews; base unchanged (0967c3ee). The pet run found review C's N3.2 test expecting "Cat Bed" refused; updated to "drafted as the vessel, never flat" (the finding's intent), to be noted on the pet PR.

- 13:40Z stop record: every unblocked queue item is pushed and in review. Remaining work is
  blocked on the integrator's decisions (P0-NEXT-PRODUCT, PR #9 colourwork, motif joins), on
  Batch 5 (stall re-drive), or on sourcing (hats); see P0_GAP_REGISTER.json. The next wake
  (the 2-hourly loop, or any PR event) polls reviews first and acts on findings and decisions.

- 15:30Z: reviews OPUS2G (#5 ACCEPT; #6, #7, #8 CHANGES_REQUIRED) and OPUS2H (#3 EF2
  ACCEPT; #9 HOLD) landed on their review branches and are being worked:
  - pushed: #8 (fa529381), #7 (4c777a0b), #5 (be96a598);
  - uncommitted, regression running:
    - #6 D-1/D-2/D-3/D-4 in /home/user/opus2-race (97 suites, /tmp/claude-0/oq5_results.txt);
    - #9 H2-1..H2-6 in /home/user/opus2-colour (/tmp/claude-0/cw3_results.txt);
    - #3 H1-1..H1-3 in /home/user/opus2-p0 (/tmp/claude-0/h1_results.txt; not
      task-tracked, so read the file).
  - D-5 (a verify check for deferred B-5) is proposed, not built: /api/verify is the
    integrator's surface.

- 16:35Z stop record: the integrator's 14:31Z work queue on PR #3 (authoritative while
  COORDINATION.json is frozen at 0967c3ee) is complete, items 1-5, with a reply mapping each
  item to its commit. The loop's poll list is widened (PR #3's work-queue comment, every
  SECREVIEW-OPUS2* branch, PRs #3 and #5-#11). Remaining work waits on:
  - re-reviews of #6, #7, #8 and #9;
  - first reviews of #10 and #11;
  - integrator decisions: P0-NEXT-PRODUCT, motif joins, D-5;
  - C-1's jobs.last_error;
  - Batch 5 (stall re-drive) and sourcing (hats).

- 19:30Z note: a same-size mutation (`= 2` → `= 0`) followed by a restore in the same second left a stale `.pyc`, so one test run used MIN_RUN=0. Caches are cleared everywhere, and the affected suites are being rerun. Rule from now on: clear `__pycache__` after every mutation check.

- 22:45Z review OPUS2J:
  - verdicts: #7 and #8 ACCEPT and merged into INTEG1; colourwork HOLD LIFTED and merged into INTEG1 (`0ef729ac`; the integrator resolved J-7); #3, #10 and #11 CHANGES_REQUIRED;
  - pushed: #3 J-1 `c3074241`; #7 J-3 tests `3468fe73`;
  - uncommitted, regression running:
    - pet bed J-9/J-10/J-11/J-12 (/tmp/claude-0/pet2_results.txt);
    - colourwork J-6/J-8b (task blfgd13lp);
    - stocking J-13/J-14/J-15/J-16, which waits for the pet push, then merges pet in and reruns.

- 23:30Z: colourwork J-6/J-8b pushed in `424d69a9`; pet bed J-9..J-12 in `7d220e01`; both commented. The stocking J-13..J-16 fixes are committed locally (`563c0436`) with the pet merge `a4a61433`, NOT pushed. The 45-suite run on the combined tree writes /tmp/claude-0/st2_results.txt (ends ST2DONE; not task-tracked, so read the file). If it is clean: push opus2/p0-stocking and comment on #11. If the container was reset: rerun those suites from the committed worktree /home/user/opus2-stock.

- 2026-11-02T00:29Z (from date -u; earlier in-flight notes on this date used approximate times): the integrator's 21:48Z queue is done except item 2. The stocking (J-13..J-16, committed `563c0436` + merge `a4a61433`, unpushed) is rerunning as tracked task bjibisyae; its first launch at 23:30Z never started (an untracked process substitution). From now on every checkpoint time comes from date -u.

## Done log
- 2026-11-02T02:03Z: stocking J-13..J-16 pushed (`563c0436`, merge `0ef8a716`), commented on #11. The integrator's 21:48Z queue is complete. Stop reason: everything is in review. Waiting on: re-reviews of #3 (J-1), #7 (J-3), #9 (J-6/J-8b), #10 and #11; integrator decisions (P0-NEXT-PRODUCT, motif joins, D-5, whether the stocking needs a sourced size); C-1 data.
- 2026-11-01T20:45Z: integrator 17:23Z queue done; PR #3 plural object nouns in `771e1e1a` (-b4merge `8f798b0a`); summary posted on PR #3. Stop reason: every queue item is pushed; waiting on re-reviews (#3, #7, #8, #9), first reviews (#10, #11), decisions (P0-NEXT-PRODUCT, motif joins, D-5) and C-1 data.
- 2026-11-01T20:00Z: #9 OPUS2I I-2/I-4/I-5/I-6/I-7/I-8 pushed in `fa02cb49`, commented; re-review requested. Every review I finding is addressed. The queue waits on: re-reviews (#3 I-1, #7 C-4, #8 F-5, #9); first reviews (#10, #11); integrator decisions (P0-NEXT-PRODUCT, motif joins, D-5); C-1 (jobs.last_error).
- 2026-11-01T19:20Z: #8 F-5 pushed in `d8d80301`, #7 C-4 in `7c3806fc`, both commented.
- 2026-11-01T19:00Z: review OPUS2I (#5, #6, #7, #8 ACCEPT; #3 I-1 MED; #9 KEEP HOLD on I-2 HIGH). #3 I-1 pushed in `6d6d83d9`, -b4merge `cd9b389b`, commented. In flight, uncommitted:
  - #9 I-2, I-4, I-5, I-6, I-7, I-8: 93-suite run in /tmp/claude-0/cw4_results.txt;
  - #7 C-4: suites in task bnnv5ho9w;
  - #8 F-5: suites in task bc3nzy5st.
- 2026-11-01T16:20Z: #9 OPUS2H H2-1..H2-6 pushed in `f57219d0` and commented. Every review G/H finding is now addressed. The queue waits on re-reviews and the three integrator decisions (P0-NEXT-PRODUCT, #9 adoption, motif joins).
- 2026-11-01T16:00Z: review G/H follow-ups pushed: #6 `23935b58`, #3 `558e7ca9` (+ -b4merge `f959e41d`), #5 `be96a598`, #7 `4c777a0b`, #8 `fa529381`; all commented. Left: #9 H2-1..H2-6 in regression (/tmp/claude-0/cw3_results.txt). #10/#11 are stacked on the older -b4merge; they merge forward cleanly (no file overlap with the H1 changes except fallback_constructions, a non-overlapping hunk).
- 2026-11-01T13:35Z: stocking pushed in `5c7b984a` with the pet-bed union merge `be12b47b`; PR #11.
- 2026-11-01T13:00Z: pet basket bed pushed in `d0a7685f`, PR #10 opened (stacked on -b4merge).
- 2026-11-01T11:40Z: PR #3 EF2 fixes pushed in `13d67502`, merged into -b4merge as
  `55450fc3`, and commented.
- 2026-11-01T11:00Z: PR #3 Batch 4 merge resolution on `opus2/p0-revenue-workforce-b4merge` `f96d7bd2` (commented). P0-CIR-COLOURWORK pushed `1073196f`, PR #9 (proposal).
- 2026-11-01T10:20Z: PR #6 EF2-6/EF2-8/B-5 pushed in `61d76d9f`; EF2-7 `ensure()` in `cc8f2b4f`; commented.
- 2026-11-01T10:15Z: P0-FAMILY-MEMBERSHIP pushed in `0f862a1b`, PR #8 opened.
- 2026-11-01T09:50Z: P1-CULTURE-SWEEP-TIMEOUT pushed in `ec97a79e`, PR #7 opened.
- 2026-11-01T09:10Z: EF2-4 + EF2-5 pushed in `e93b16ed` (PR #5, commented).
- 2026-11-01: review E fixes pushed in `0e941757`, F-A in `b42f4245`, F-B in `007f5d1c`;
  OPUS2EF2 re-review returned CHANGES REQUIRED (06:50Z).
