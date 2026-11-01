# OPUS2 engineering checkpoint (read first on every wake)

Updated: 2026-11-01T10:00Z. The engineering loop rewrites this file at the end of every work
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

## Done log
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
