# OPUS2 engineering checkpoint (read first on every wake)

Updated: 2026-11-12T02:30Z. The engineering loop rewrites this file at the end of every work
unit and pushes it to `origin/opus2/checkpoint`. A container reset loses /tmp and the
worktrees, not this file.

## State at 2026-11-12T00:00Z (read first)
- 93eb5106 is certified (10867/0). 88d1ce5e (Batch 7) was DEPLOYED at 2026-11-12T02:18Z; verify 13/14, with
  a dead letter from about 00:1xZ (the pre-spread midnight window).
- The cadence-spread review 6810462823 was DO NOT SHIP over test strength: the oracle read
  the code under test, and the next-wake checks were grep-only. Fixed in 5f4a175e on
  opus2/cadence-spread (delta on 86e0054d). RR 6811526498 is on #28.
  - The oracle is a fixed 12 h; company and status next_wake are checked by value.
  - Main's 4 survivors are killed; 12 suites green, including resume_runner, oauth_callback
    and vacuity.
  - Next: wait for Main's verdict, then act on it.
- 01:30Z and 02:30Z wakes: there is no new [MAIN] message after 6810462823. COORDINATION has not changed
  since 11-08, and no new review branch has findings on opus2 code.
- 18d9ab28 (L LOWs) is still RR 6782981520.
- Standing lesson: a new verify check or a sleep/timeout/now() test also runs
  test_etsy_oauth_callback and test_w4_resume_runner. Run test_vacuity on every change.
- OWNER-GATED: readiness_from_export on a production export; Etsy's required property at
  create time.
Stop reason: everything is review-requested; waiting on Main's verdicts on 5f4a175e and 18d9ab28.

## State at 2026-11-11T11:40Z (superseded)
- Main's certification of 64547be5 FAILED on stale tests. Two were my P1 misses:
  - the verify check-list pin in test_etsy_oauth_callback;
  - suite_final_segment declarations for the clock-sensitive p1 suites.
  Main fixed them in 93eb5106, which is on INTEG1; a fresh certification follows.
  Run nothing on Main's machine during it.
- LESSON, standing rule: a change that adds a /api/verify check, or a test file using sleep,
  timeout= or now(), also runs test_etsy_oauth_callback.py and test_w4_resume_runner.py
  before its RR.
- opus2/cadence-spread @ b23d92a1 (93eb5106 merged in): resume_runner, oauth_callback and
  cadence_spread are green. RR 6793458835 is queued behind certification.
- 18d9ab28 (L LOWs) is still RR 6782981520.
- OWNER-GATED: readiness_from_export on a production export; Etsy's required property at
  create time.
Stop reason: everything is review-requested; waiting on Main's verdicts after certification.

## State at 2026-11-11T10:45Z (superseded)
- eb699706 was SHIPped and merged into w6-INTEG1 as 64547be5 (6791709875). Main is running
  full certification on 64547be5; don't ask for reviews that run suites on its machine.
- opus2/cadence-spread (worktree opus2-cs) @ 90f90220, RR on #28, holds three commits:
  - the stagger, 52af7832;
  - a merge of 64547be5;
  - the nits: legacy bare incident rows resolved, a deploy.sh re-read WARN test,
    WARN_EXIT = 10.
  - 3/3 nit mutants and 5/5 stagger mutants killed; 20 suites green.
  - Open question to Main: should any daily cadence stay at 00:00Z?
- 18d9ab28 (L LOWs) is still RR 6782981520.
- OWNER-GATED: readiness_from_export on a production export; Etsy's required property at
  create time.
Stop reason: everything is review-requested; waiting on Main's verdicts on 90f90220 and 18d9ab28.

## State at 2026-11-11T09:00Z (superseded)
- b4b6c01d was SHIPped and merged into w6-INTEG1 as 5e6d43e7 (6789501427).
- Its follow-ups are on opus2/p1-warn-followups (worktree opus2-wf) @ eb699706, RR on #28:
  - LOW-1: readback exits 3 on WARN, and deploy.sh deploys on it; the board ignores WARN;
  - LOW-2: the incident is per instance, via open_or_restate with orphan resolution;
  - the nits.
  - 8/8 mutants killed; 12 suites green.
- Also open, awaiting Main: 52af7832 (cadence spread, opus2/cadence-spread) and 18d9ab28
  (L LOWs).
- OWNER-GATED: readiness_from_export on a production export; Etsy's required property at
  create time.
Stop reason: everything is review-requested; waiting on Main's verdicts on eb699706,
52af7832 and 18d9ab28.

## State at 2026-11-11T07:15Z (superseded)
- Open RRs, all waiting on Main:
  - b4b6c01d, the P1 review fixes on opus2/p1-worker-nightly-stall (6787274305);
  - 18d9ab28, the L LOWs on opus2/l-followups-2 (6782981520);
  - 52af7832, the midnight-herd spread on opus2/cadence-spread (worktree opus2-cs, RR on #28).
- Cadence spread: daily cadences get a stable sha256 offset and key cadence:<name>:s<window>.
  A one-time legacy guard prevents a double run on the deploy day. Sub-daily keys are
  unchanged. 5/5 mutants killed; 19 suites green.
  - Asked Main whether any daily cadence must stay at 00:00Z.
- OWNER-GATED: readiness_from_export on a production export; Etsy's required property at
  create time.
Stop reason: everything is review-requested; waiting on Main's verdicts.

## State at 2026-11-11T05:00Z (superseded)
- P1 nightly stall: Main's changes-requested 6785727146 on 23d5649c is addressed by
  b4b6c01d on opus2/p1-worker-nightly-stall (worktree opus2-ws), RR 6787274305.
  - handler_long is a degraded basis after 15 min, with a P2 incident raised and resolved
    by the scheduler loop and an advisory /api/verify check.
  - ops/readback has a WARN verdict, and a warn-only row never goes above WARN.
    rollback_decision does not contain on WARN.
  - The env clamp and the F3 tests are in.
  - 15/15 mutants killed; 20 suites green.
- opus2/l-followups-2 @ 18d9ab28 is RR 6782981520, awaiting a verdict.
- Next follow-up, after the P1 merges: the midnight herd (a per-cadence hash offset plus a
  duplicate-run guard).
- OWNER-GATED: readiness_from_export on a production export; Etsy's required property at
  create time.
Stop reason: everything is review-requested; waiting on Main's verdicts on b4b6c01d and 18d9ab28.

## State at 2026-11-11T01:45Z (superseded)
- P1 6783107211, the nightly worker_alive false at ~00:14-00:20Z.
  - Fixed on opus2/p1-worker-nightly-stall (worktree opus2-ws) @ 23d5649c, RR on #28;
    ACK 6783315420 has the root cause.
  - Cause: every daily cadence window opens at 00:00Z, and a ~7 min handler blocks the
    runner tick, which is written only between jobs.
  - Fix: liveness counts a handler running within MAX_HANDLER_SECONDS as alive (Worker.current).
    A wedged worker, or one over budget, still reads dead.
  - 6/6 mutants killed; 16 suites green.
  - Proposed separately: spreading the midnight burst (it changes the idempotency windows).
- opus2/l-followups-2 @ 18d9ab28 (the 6781897314 LOWs) is RR 6782981520, awaiting a verdict.
- OWNER-GATED: readiness_from_export on a real production export (the operator credential);
  Etsy's required property at create time.
Stop reason: everything is review-requested; waiting on Main's verdicts on 23d5649c and 18d9ab28.

## State at 2026-11-11T00:00Z (superseded)
- 8e9ac195 was SHIPped and merged into claude/w6-INTEG1 as 074d6f43 (6781897314).
- The LOWs from that review are on opus2/l-followups-2 (worktree opus2-lf2) @ 18d9ab28,
  RR 6782981520:
  - whole-token shortfall keys;
  - the search judgement runs outside the try;
  - dispose() is in a finally;
  - the docstring is rewrapped.
  - 4/4 mutants killed; 5 suites green.
- OWNER-GATED, not ours (Main 6781897314):
  - Running readiness_from_export.py on a real production export needs the operator
    credential. Neither Main nor opus2 holds it. So F-848 stays OPEN/PARTIAL until the
    owner runs it or provides a read-only credential.
  - Etsy's real behaviour for required properties at create time is verified only by
    the live round trip.
Stop reason: everything is review-requested; waiting on Main's verdict on 18d9ab28.

## State at 2026-11-10T21:00Z (superseded)
- opus2/l-followups (worktree opus2-lf) @ 8e9ac195, RR 6778725878. This fixes Main's
  DO NOT SHIP 6776323331 on d1eb85db and the L3 F1/F3 details (6775786220):
  - test_vacuity is green again (it is now in every regression set);
  - the restored-copy deletion is proven (c2 and c3 killed);
  - why_unmet derives why from each requirement's own evidence;
  - the LOWs are done.
  - F1: the past-shadow PASS path is tested. It found my L3 defect: fake_etsy's
    required_property refused every create. The new knob is
    create_refuses_required_property, default True.
  - F3: the stale search defect is re-judged after the taxonomy re-run.
  - 7/7 mutants killed; 17 suites green.
- Main will run scripts/readiness_from_export.py on a fresh production export once this
  branch merges (item 5).
Stop reason: everything is review-requested; waiting on Main's verdict on 8e9ac195.

## State at 2026-11-10T18:45Z (superseded)
Batch 6 (b7921052) was deployed 2026-11-10T15:22Z. Main verdict 6773190553: L0 3d956a89,
L3 35d6a9ab and L4 9f46d341 are all SHIP and merged into claude/w6-INTEG1 (be4d1490). L1/L2
are closed via the integrated F-834/F-846 overrides (e5c702f9). F-848 stays OPEN/PARTIAL.
- Follow-ups 6773190553 are on opus2/l-followups (worktree opus2-lf, cut from be4d1490) @
  d1eb85db, RR 6775471763:
  - #1: the exhausted incident resolves;
  - #2: slots floor test (M-c);
  - #4: readiness_explained on a refused transition (sustainable_economics =
    INSUFFICIENT_DATA on a fresh DB; no_open_incidents passes in fast mode);
  - #5: scripts/readiness_from_export.py (operator-gated export, judged read-only);
  - #6: L0 M10 and a narrow has_table catch.
  - Mutants 9/9; 15 suites green.
- OPEN: #3, L3 F1 (a surviving mutant). Its details are in reviewer notes I cannot see;
  QUESTION asked in 6775471763.
- Next production-mode rehearsal (run alone) will name the incident behind
  no_open_incidents.
Stop reason: everything is review-requested; waiting on Main (F1 details + verdict on d1eb85db).

## State at 2026-11-08T18:30Z (superseded)
Owner goal 6719266602 (listing agents done, tested and autonomous): L0-L4 are all built and
review-requested.
- L0 P0-PHYSICAL-UPGRADE-PROVENANCE (opus2/l0-physical-upgrade-provenance, worktree opus2-l0):
  f3258d75 -> delta e0f903b3 (HIGH-1 asset fingerprints, no STALE halt) -> hardening 3d956a89.
  Preliminary SHIP by Main.
- L1/L2 (F-834/F-846): no code. The accepted TESTED overrides were never promoted to
  overrides.json; a dry run makes both COMPLETE. QUESTION 6719302210 is unanswered.
- L3 F-848 (opus2/l3-shadow-rehearsal-package, worktree opus2-l3) @ 35d6a9ab, RR 6725345928:
  - the rehearsal now covers the listing package, an 8-product production-shaped catalogue,
    a simulated taxonomy (with an assumed Crochet property) and the owner grant;
  - it is blocked only by the owner phase transition;
  - production-mode evidence for eb72853 is committed.
- L4 P0-NEXT-PRODUCT (opus2/l4-next-product, worktree opus2-l4) @ 9f46d341, RR 6724065439:
  the WIP gate, parked jobs, in-flight skip, and the exhausted incident.
- Engineering unknown on the critical path: Etsy's real taxonomy has no crochet node. The
  category needs a "Crochet" value in the Patterns & Blueprints schema, which needs a
  production refresh read (LAUNCHFIX section 4).
- Lessons:
  - The production-mode rehearsal had a premature-settle race, now fixed. There is also an
    intermittent unclaimed in-process job; retried and diagnosed, root cause unknown.
  - Run production-mode rehearsals alone.
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-08T01:05Z (read first)
- Main 6715006286: wraptest e831dc6a SHIP (it is in the Batch 6 certification head).
  Visual b3dcb121 was DO NOT SHIP with three surviving mutants.
- REVIEW-REQUESTED:
  - Visual 695f416d (opus2/visual-an1-an3, worktree opus2-a1v): B-N1 SN2_no_id_order,
    B-N2 SN2_no_jobtype, B-N3 AN3_reverify_raw are killed (tests only). 6715351641.
  - Wraptest LOWs cc1216bd (opus2/wraptest-lows, worktree opus2-wrap): A-L2 moved to
    visual.experiment.anchor_lookup; A-L1 binding pinned (3/3 mutants); INFO renames. 6715400340.
  - A1 nouns 0e2d5f36: ships with the A1 unit (Codex).
  - PHYSICAL 1a818679: its base waits on Codex.
- Lesson: list EVERY mutant Main names; claiming "N/N" while leaving one out cost a round.
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-07T23:40Z (read first)
- Main 6713597156: 7eeeac92 SHIP (integrating). fc26887b DO NOT SHIP standalone (ships with the A1 unit).
- REVIEW-REQUESTED:
  - Wraptest e831dc6a (opus2/wraptest-fix, worktree opus2-wrap), the Batch 6 blocker for
    6712715069. Dry run uses option (b). The live run adds V0 activation in the scratch DB,
    the reservation fix, the experiment anchor lookup and distinct fake deliveries.
    5/5 mutants killed. 6714238886.
  - A1 nouns 0e2d5f36 (opus2-a1n): B-N1 words/phrases/CamelCase/stems, B-N3 pet toy, B-N4.
    44/44 mutants killed. 6714241176.
  - Visual A-N1..3 b3dcb121 (opus2/visual-an1-an3, worktree opus2-a1v). 6/6 mutants killed. 6714297866.
  - PHYSICAL 1a818679: its base waits on Codex.
- Pre-existing on w6-INTEG1 f706e12d: test_w4_visnext2 has 4 failures (prompt-builder 2.1.0/2.1.1 drift
  x3, pytest monkeypatch x1). These are not opus2's; reported in 6714238886.
- Lesson: fake transports that return identical bytes trip V1's duplicate-bytes negative-decision hold.
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-07T19:10Z (read first)
- SHIPPED and integrated: storefront, portfolio, visual D1/D2/D4, #7 M-5 (w6-INTEG1 a792f664).
- REVIEW-REQUESTED:
  - PHYSICAL delta 1a818679 (worktree opus2-ptr2): tester_roster work item, no owner card. Its
    Codex base still waits on Codex.
  - A1 infant nouns fc26887b (opus2-a1n, leaf on opus2/p0-child-safety-core).
  - A-1..A-4, S-N2, S-N3 at 7eeeac92 (opus2-a1v, branch opus2/visual-a1-a4).
- Lesson: page #28 by total count (issue get -> comments, perPage 2 page = ceil(n/2)). Comments
  were missed before.
- Disk: the cloud disk filled up with mutant copies. Delete each copy after its run.
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-07T16:20Z (read first)
- VISUAL d6b642dd + V6 80765387: SHIP, integrated in w6-INTEG1 fbddf746.
- Follow-ups D1/D2/D4 at opus2/visual-d1-d2-d4 256378d6 (worktree opus2-d1): REVIEW-REQUESTED.
- STOREFRONT ff573af8 and PORTFOLIO 77bf3e19, rebased on INTEG1 59681a47: REVIEW-REQUESTED.
- PHYSICAL e8b458b5 and #7 49a27769 are in Main's queue.
- Do not use `find ... -exec rm -rf` in a background shell: the safety check blocks it.
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-07T15:30Z (read first)
- STOREFRONT review a1331372 (DO NOT SHIP: H1, M1, M2) is fixed at 06a00c91; REVIEW-REQUESTED. A live
  gallery is never rebuilt (LIVE_WHY). Candidate-set store offered as follow-up after Main's A3 F2.
- PORTFOLIO review ee5dbeee (DO NOT SHIP: N1) is fixed at fdd077f6; REVIEW-REQUESTED.
- VISUAL d6b642dd, V6 80765387 and PHYSICAL e8b458b5 are in Main's queue. #7 M-5 is at 49a27769.
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-07T13:15Z (read first)
- VISUAL: review 8427e777 was DO NOT SHIP (N1-N5). Fixed on opus2/visual-on-integ1 @ d6b642dd (worktree
  opus2-visi; merges w6-INTEG1 5913931f) and V6 on opus2/v6-on-integ1 @ 80765387. REVIEW-REQUESTED.
  The *-on-v1 branches are superseded.
- PORTFOLIO-fo ee5dbeee and STOREFRONT-fo a1331372 on fix-only 0f2de815: REVIEW-REQUESTED.
- PHYSICAL on Codex e8b458b5: REVIEW-REQUESTED.
- #7: M-5 only (test) REVIEW-REQUESTED @ 49a27769; Codex adopts M-6 into V0 (Main 6707471647).
- Base issue (not ours): test_w3_k12_model_photography fails on INTEG1 5913931f (V0 not_activated).
Stop reason: everything is review-requested; waiting on Main.

## State at 2026-11-07T10:40Z (read first)
| Item | Branch | Head | State |
|---|---|---|---|
| PHYSICAL | opus2/physical-sample-request-on-codex | e8b458b5 | REVIEW-REQUESTED; supersedes d697d093 (withdrawn) |
| VISUAL stack on V1 | v2/v4/v5/v3-on-v1 | top 8427e777 | in Main's independent review; HOLD changes |
| V6 on V1 | opus2/v6-on-v1 | 60747f7e | REVIEW-REQUESTED; option (a), V1-SCENE-END-BANDS |
| STOREFRONT-fo | opus2/p0-storefront-asset-fix-fo | a1331372 | REVIEW-REQUESTED on fix-only 0f2de815 |
| PORTFOLIO-fo | opus2/p0-portfolio-act-fo | ee5dbeee | REVIEW-REQUESTED on fix-only 0f2de815 |
Next after verdicts: rebase #7 onto w6-INTEG1; fold #3 onto codex quality-a1-a2 after U2; #9 fixes.
Stop reason: everything assigned is review-requested or on hold for Main's verdicts.

## State at 2026-11-07T08:50Z -- Main module map 6703941388 (read first)
- Ownership has changed: adopt Codex heads for A3/A9/A4/A5/A7/A8, never rebuild them. Codex owns V0 and A6.
- PHYSICAL: folded onto codex/physical-complete-colour-evidence 77b9a88f as
  opus2/physical-sample-request-on-codex @ e8b458b5 (worktree opus2-ptr2). The 50-suite regression (ptr2) is
  running -> post a REVIEW-REQUEST, then withdraw the old opus2/p0-physical-test-request.
- VISUAL: rebased onto codex/v1-craft-enum ded427f6 (worktree opus2-vis). Stack: v2-on-v1 8bca3606 ->
  v4-on-v1 16d8ccfd -> v5-on-v1 6feab785 -> v3-on-v1 8427e777 (top). REVIEW-REQUESTED in 6704648481.
  visnext2's 3 failures are the same on pristine V1 (builder 2.1.1 not re-frozen).
- V6 on V1 (opus2/v6-on-v1, worktree opus2-v6b, local): BLOCKED. On V1, end-band scene frames read
  craft UNKNOWN. Asked Main to choose (a) name it as a gate, (b) a different design, or (c) a Codex check.
- STOREFRONT on fix_only @ 8094601b (the cards name each other). PORTFOLIO-fo @ d564a059. Both wait for
  Main's fix-only verdict.
- Old PRs: keep #7, #9 and #3 (fold #3 onto codex quality-a1-a2 after U2); park #22.
- pytest is now installed; the Codex suites need `python3 -m pytest`.
Stop reason: waiting on Main's verdicts and the V6 decision; the PHYSICAL regression is in progress.

## State at 2026-11-07T08:10Z (read first)
Every opus2 item is REVIEW-REQUESTED on #28. Nothing is integrated or certified. fix_only is at 9e8665c3.
| Item | Branch | Head |
|---|---|---|
| PHYSICAL | opus2/p0-physical-test-request | d697d093 (6703757948) |
| PORTFOLIO on fix_only | opus2/p0-portfolio-act-fo | d564a059 (6704258374) |
| STOREFRONT on fix_only | opus2/p0-storefront-asset-fix-fo | 59233ee5 |
| V2 fix | opus2/v2-vessel-fidelity | 25a41a7c (6703834356) |
| V3 fixture-only | opus2/v3-identity-fixture | 50931f5b (6703834356) |
| V4 / V5 | v4-scene-references / v5-scale-verification | 86cf2a36 / 295474c6 |
| V6 preview | opus2/v6-gallery-e2e | c7aba05b (6703927955) |
Stop reason: everything assigned is review-requested. Waiting on Main's verdicts; the next step is fixing what they return.

## State at 2026-11-07T07:15Z -- owner "P0 FINAL COMPLETION DIRECTIVE" (read first)
OA-V3-LAURA-QUALIFICATION is APPROVED FIXTURE-ONLY; Main verified it (#28 6703390021). Main's fix_only branch is claude/w6-fix-only-rebuild @ 6cbc08e6.
| Item | Branch / worktree | Head | State |
|---|---|---|---|
| PHYSICAL | opus2/p0-physical-test-request (opus2-ptr) | d697d093 | REVIEW-REQUESTED #28 6703757948; 44 suites (owner_queue_race load-timeout, passes clean) |
| PORTFOLIO on fix_only | opus2/p0-portfolio-act-fo (opus2-pact2) | uncommitted | SEO -> listing.seo fix_only; focused 11/11; regression pfo + mutants running; merge 6cbc08e6 before push |
| STOREFRONT on fix_only | opus2/p0-storefront-asset-fix-fo (opus2-sfa2) | worker af18da9d | fixes review d8b2754b F1-F7; told to merge 6cbc08e6 |
| V2 fix of review 1688b97f | opus2/v2-vessel-fidelity (opus2-v2) | uncommitted on 6799f1d4 | F1-F7 + F10 done; 11 mutants killed; regression v2f running |
| V3 fixture-only | opus2/v3-identity-fixture (opus2-v3) | worker abe11379, uncommitted | regression running |
| V6 | opus2/v6-gallery-e2e (opus2-v6) | 9365876f pushed | done per I-V6-ACCEPTANCE; must re-merge the fixed V2 before review |
| V4 / V5 | - | 86cf2a36 / 295474c6 | in Main's review queue |

## State at 2026-11-07T05:50Z (read first)
Every branch is from claude/w6-INTEG1 @ f5c3976d. Worktrees are /home/user/opus2-{ptr,pact,sfa,v2,v4,v5}.
| Item | Branch | Head | State |
|---|---|---|---|
| 2 P0-PHYSICAL-TEST-REQUEST | opus2/p0-physical-test-request | d697d093 | regression 20/44 green, test_product_run running (resume: /tmp/claude-0/resume.sh ptr ...) -> REVIEW-REQUEST |
| 3 P0-PORTFOLIO-ACT | opus2/p0-portfolio-act | ad351e46 | review e1d1adb3 DO NOT SHIP fixed (F1-F8); REVIEW-REQUESTED #28 6703009305; 14/14 |
| 4 P0-STOREFRONT-ASSET-FIX | opus2/p0-storefront-asset-fix | d8b2754b | REVIEW-REQUESTED, queued at Main |
| V2 | opus2/v2-vessel-fidelity | 6799f1d4 | REVIEW-REQUESTED #28 6702941320 (I-V2-UNJUDGED-PAIRS applied); 13/13 |
| V4 | opus2/v4-scene-references | 86cf2a36 | REVIEW-REQUESTED #28 6703009305; 11/11 |
| V5 | opus2/v5-scale-verification | 295474c6 | REVIEW-REQUESTED #28 6703009305 |
| V3 | - | - | BLOCKED: touches Laura identity scoring; asked Main (#28 6702941320) |
| V6 | - | - | proposed "demonstrate, not certify" (F-852/F-853 owner gates); awaiting Main |
Stop reason: everything assigned is built and review-requested, except item 2, which is waiting on its regression, and V3/V6, which wait on Main's decisions.

## State at 2026-11-07T05:20Z -- Main ASSIGN 6701113204 / 6701702761, items 2-5 (read first)
Every item is branched from claude/w6-INTEG1 @ f5c3976d. Worktrees are /home/user/opus2-{ptr,pact,sfa,v2}.
| Item | Branch | Head | State |
|---|---|---|---|
| 2 P0-PHYSICAL-TEST-REQUEST | opus2/p0-physical-test-request | d697d093 pushed | focused 6/6, 9 mutants killed; 44-suite regression running (/tmp/claude-0/ptr_results.txt) -> REVIEW-REQUEST when green |
| 3 P0-PORTFOLIO-ACT | opus2/p0-portfolio-act | f3bea437 pushed | REVIEW-REQUESTED (#28 6702476082); regression 14/14 |
| 4 P0-STOREFRONT-ASSET-FIX | opus2/p0-storefront-asset-fix | d8b2754b pushed | REVIEW-REQUESTED (#28 6702476082); regression 11/11 |
| 5 V2 P0-c vessel verifier | opus2/v2-vessel-fidelity | e30b5fa0 pushed | REVIEW-REQUESTED (#28 6702674398) |
| 5 V2 P1-d + P2-a | opus2/v2-vessel-fidelity | 22940594 pushed | focused 4/4 + 3/3, mutants all killed; 13-suite regression running (v2r_results.txt) -> REVIEW-REQUEST |
Open decision for Main: whether unjudged frames should block P1-d. Merge note: items 3 and 4 both regenerate autonomy_map.json; regenerate it on the merged tree.
Next: V3-V6. Fixtures only, per Main's constraints. V3 needs a funded vision model (V0), so build only its fixture or decision layer.

## State at 2026-11-07T01:45Z (read this before the older sections below)
Stop reason: no unduplicated assigned work remains. Waiting on Main for a new assignment.
- Issue #28: no [MAIN] message since my 2026-11-03T01:30Z REVIEW-REQUEST (V0 76fc0f3d). Newest
  comment is the Codex continuity checkpoint of 2026-11-04T08:14Z.
- Regressions finished green after the container restart:
  - A1R c3a7b93a: 73/73 suites exit 0.
  - A2F 52f83cf7: 84/84 suites exit 0.
- Codex has continued every opus2 handoff. Do not rework these lines:
  - Codex's cumulative review-only preview PR #130 (ac57b78) contains 11 of the 13 opus2 heads
    (A1R, A2F, A3, A4a, A4b, A5, A7, A8, A9, V1). It passes 169/169 on SQLite and is marked
    DO NOT INTEGRATE.
  - V0 76fc0f3d continues on codex/v0-provider-authority (PR #40). Codex found financial
    defects there: reservation release race, ID reuse, negative/zero billing, probe scope.
  - A6 594d5e38 is an ancestor of every codex/a6-* branch. Those branches already carry the
    rehearsal fixture corrections and the rendered-output assertion.
- A4A local fixes were not pushed. Codex PR #33 (040fdf4) covers dishcloth size and Product
  Truth. Codex also showed that a stop/reopen without a per-gap ownership transaction races,
  and my A4A-3 reopen has that flaw.
  - Diff saved as opus2_wip/A4A_local_wip_on_3dc3e68c.patch, and as git stash@{0} in
    /home/user/opus2-a4a.
  - Reuse only the OBJECT_SIZE_BANDS / check_object_size_claims idea, and only if Codex asks.
- 03:31Z: Main's verdicts e846a2ab say A6 8c131f10 and A7 83fe31d2 are DO NOT SHIP. A7-1 is
  already fixed on Codex 677661ec (PR #129 b4814be): verified, posted on #28 (6701682843).
  Main notes A6 is superseded by the codex/a6-* lines. Batch 6 base claude/w6-INTEG1 exists.
- Next action: wait for a [MAIN] ASSIGN on #28. Do not start new work on handed-off lines.

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

## State at 2026-11-02T20:21Z -- owner directive "IMMEDIATE P0 EXECUTION AND COORDINATION"
Priority (owner): A1-R + A2 push and delta reviews -> A4b published -> A3D-1 -> A6 -> A8.
Do NOT touch A4(a), A5, A7 or A9 (Main's workers). No new product-specific generators.
| Item | Branch / worktree | Head | Tests | State / next action |
|---|---|---|---|---|
| A1-R children's safety core | opus2/p0-child-safety-core, /home/user/opus2-a1r (base INTEG1 7c42e706) | 1dd257be (local) | part1 29/29, part2 29/29; test_product_run running alone | push + open PR to claude/w5-INTEG1 + PR #3 delta-review request when product_run passes |
| A2 v2 name/object | opus2/a2-name-object (PR #26), /home/user/opus2-a2 | c93f9c53 (local; PR has 3be8262f) | 45-suite run in progress; test_fallback_draft_provenance fixed (c93f9c53); test_opus2_draft_constructions asserts "Bobble Cushion" -> PANEL_PAIR, now deliberately REFUSED (bobble texture not made) -- update that assertion after the run | push + PR #26/#3 comment |
| A4b enrichment | opus2/a4b-enrichment (PR #27), /home/user/opus2-a4b | 230b7d8d pushed | focused green; 8 mutants killed | request review on PR #3 |
| A3D fixes | opus2/p0-photo-asset-review (PR #23), /home/user/opus2-photo | c2174947 (local; 637e011f SHARED physical_upgrade lock) | test_opus2_photo_asset_review 23/23, 8 mutants killed incl. K7/K9/K12; focused regression (12 suites) running | push + PR #3 comment |
| A6 learning into design | opus2/a6-learning-to-design, /home/user/opus2-a6 (from handed WIP 7c9306e3 on INTEG1) | ebead3dd pushed (no PR yet) | test_w5_a6_learning_to_design 6/6, 11 mutants killed; 38-suite focused regression running | open PR to claude/w5-INTEG1 when green; PR #3 comment |
| A8 culture to ideation | not started (COORDINATION: depends_on A4a, owned by Main's worker) | - | - | check A4a branch claude/w5-A4a-research-to-concept for the concept_intake path; build A8 on it or on INTEG1 without duplicating A4a |

| A4a research to concept | opus2/a4a-research-to-concept, /home/user/opus2-a4a (from claude/w5-A4a 993cc0cd) | 3dc3e68c pushed | 9/9 (test through compile + certify: granted) | REVIEW-REQUEST posted on #28 |
| A9 package event | opus2/a9-package-event, /home/user/opus2-a9 (from 6ee81c19) | unchanged | handoff suites queued (/tmp/claude-0/queue_a9_a7.sh, a9_results.txt) | checkpoint + review when green |
| A7 supply stall | opus2/a7-supply-stall, /home/user/opus2-a7 (from 83fe31d2) | unchanged | handoff suites queued after A9 (a7_results.txt) | checkpoint + review when green |
| A5 correction loop | claude/w5-A5-correction-loop @ 717c7925 | not taken yet | run test_cert_rebuild_chain, test_cert_parity_copy, test_disclosed_render_runtime, test_cert_design_pipeline | then review |
| V1 visual correctness | claude/w5-V1-visual-correctness @ f349c755 | not taken yet | re-run test_w4_visnext + V1 test, shadow, swarm, launch0 | owner must re-authorise the re-pinned Cloudline experiment |
| V0 | SHA pending from Main | - | - | - |

## STATE 2026-11-02T23:31Z (supersedes the tables above; channel = Issue #28)
| Item | Branch @ head | Review state | Next |
|---|---|---|---|
| A1-R | opus2/p0-child-safety-core @ c3a7b93a (48bc30c0 SHARED one fold) | A1R review DO NOT SHIP -> all 7 findings fixed; 18/18; 13 mutants killed, 1 equivalent | 75-suite regression running (/tmp/claude-0/a1r_reg.sh -> a1r3_results.txt; may hit 2h cap: resume the rest) -> REVIEW-REQUEST |
| A2-FIX | opus2/a2-name-object @ 77c3c824 (merged A1-R: _motif_fold = text_fold.fold) | A2F review in flight on 51f87859 | regression queued (a2m_reg.sh); integrate AFTER A1-R |
| A3-FIX | opus2/p0-photo-asset-review @ c2174947 | A3F review in flight | wait |
| A4a | opus2/a4a-research-to-concept @ 3dc3e68c | A4A-REVIEW in flight | wait |
| A4b | opus2/a4b-enrichment @ e230545c | review in flight (incl. retention fix) | wait |
| A5 | opus2/a5-correction-loop @ 717c7925 (unchanged) | review in flight | wait |
| A6 | opus2/a6-learning-to-design @ 8c131f10 | review in flight | - |
| A6 codex contract | opus2/a6-codex-contract @ 594d5e38 (WIP) | BLOCKED on CODEX2-3 (held-out manifest vs INTEG1) | merge Codex re-freeze, run tests/test_w5_a6_frozen_knowledge.py |
| A7 | opus2/a7-supply-stall @ 83fe31d2 (unchanged) | review requested | wait |
| A8 | opus2/a8-culture-ideation @ 4f99bd8f (on A4a) | queued behind A4a review | wait |
| A9 | opus2/a9-package-event @ 6ee81c19 (unchanged) | review requested | wait |
| V0 | opus2/v0-paid-provider-gate @ 76fc0f3d | 9 + 6 failing suites fixed via tests/_paid_activation.py | 25-suite re-run (v0b_results.txt) -> REVIEW-REQUEST; flagged same-day identical-request refusal to Main |
| V1 | claude/w5-V1-visual-correctness @ f349c755 | not taken yet | re-run test_w4_visnext + V1 test, shadow, swarm, launch0 |
Worktrees: opus2-a1r, opus2-a2, opus2-photo, opus2-a4a, opus2-a4b, opus2-a5, opus2-a6, opus2-a6c, opus2-a7, opus2-a8, opus2-a9, opus2-v0, opus2-dispatch, opus2-ckpt.

CHANNEL: GitHub Issue #28 is the official Main <-> Secondary channel ([SECONDARY] ACK posted 20:30Z).
Events: `python3 ops/assignments.py event opus2 <ID> <kind> [--sha] --push` from /home/user/opus2-dispatch
(detached at origin/claude/w4-INTEG8-next; writes only dispatch/events/opus2.jsonl).
Wake: trigger trig_01CVgKQwWxy9oSXMgTYAjUzf hourly at :28 (platform minimum 1h; */5 rejected).
Blockers: none.

## Worktrees
- `/home/user/opus2-p0`: `opus2/p0-revenue-workforce` (PR #3; review fixes only)
- `/home/user/opus2-ami`: `opus2/p0-amigurumi` (PR #18, base claude/w5-INTEG1)
- `/home/user/opus2-reg`: `opus2/p0-construction-registry` (PR #22, base opus2/p0-amigurumi)
- `/home/user/opus2-photo`: `opus2/p0-photo-asset-review` (PR #23, base claude/w4-INTEG8-next)
- `/home/user/opus2-pouch`: `opus2/p0-pouch` (PR #25, base claude/w5-INTEG1; Q16 split)
- `/home/user/opus2-colour`: `opus2/p0-cir-colourwork` (PR #9)
- `/home/user/opus2-stock`: `opus2/p0-stocking` (PR #11)
- `/home/user/opus2-a1r`: `opus2/p0-child-safety-core` (A1-R)
- `/home/user/opus2-a2`: `opus2/a2-name-object` (PR #26)
- `/home/user/opus2-a4b`: `opus2/a4b-enrichment` (PR #27)
- `/home/user/opus2-a6`: `opus2/a6-learning-to-design` (A6)
- `/home/user/opus2-ckpt`: `opus2/checkpoint` (this file)

## State at 2026-11-02T15:55Z -- integrator assignments A1-A9 (COORDINATION c25c6f1a; PR #3 status 6579974579)
Rule for A-items: branch from newest claude/w5-INTEG1; tests on a real SQLite file + DurableQueue +
Worker + registered handlers, no mocks.
- A1 DONE/pushed: PR #18 98d216b0 (6ab946ff gate + T-5; 98d216b0 durable proof), 46 suites green.
- A2 DONE/pushed: PR #26 opus2/a2-name-object 3be8262f (base INTEG1), 43/44 (listready fails on base too).
- A3: OPUS2W (DO NOT SHIP, 2 MED) fixed + pushed PR #23 8d98bf4c (INTEG1 merged 6316d5c4; decision
  I-A3-NONQUALIFYING-PHOTO implemented: terminal reason, excluded from set e6a1ef82, re-opened on qualify).
- Registry PR #22 pushed da4f331a (enrichment consumer, department flow, amigurumi merge, OPUS2V-5/6/7).
- NEXT: A4(a) per the design below, on a fresh branch from newest INTEG1.
- A4: enrichment consumer + department flow on opus2-reg (unpushed 823a82dd, b0c66556).
  A4(a) design (not started): (1) _score_coverage_handoff unanswered branch opens a research task
  (research_agent.request_research) carrying an ideation brief {gap, pod, arena}, idempotent per
  gap; (2) new deterministic step after research.investigate: answer a gap task from recorded
  competitor observations (dated listing counts/prices = fact-grade with dated sources, confidence
  recorded) and attach_proposal a flat_rows concept (intake only compiles flat_rows) whose title
  comes from the pod noun + a non-competitor descriptor; (3) radar.concept_intake approves ->
  radar.score -> cir.draft (radar.intake provenance); second run enqueues nothing. Check originality
  vs observed listings. A4(b): re-draft key draft:<slug>:<fingerprint> on enrichment.
- Decisions open: catalogue motif_promise (9 titles), non-qualifying photo frames, Cosy Baby Blanket.

## Dependencies (exact)
See P0_GAP_REGISTER.json `opus2_open_engineering`.

## Log (older entries)
## Old worktrees and queue (superseded)

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

- 2026-11-02T02:42Z — K-4 pushed on opus2/p1-culture-sweep-timeout (e0be7c4d), PR #7 commented. Pending: K-5/K-6a (#9) and K-7/K-8/K-9 (#10) regressions running; then stocking merge (#11).
- 2026-11-02T02:50Z — K-5/K-6a pushed on opus2/p0-cir-colourwork (d4486b8c), 21 suites clean, PR #9 commented. Pet bed regression still running.
- 2026-11-02T04:05Z — tapestry baskets pushed (opus2/p0-tapestry 67b67015, PR #15; 15/16 suites, launchfix fails identically on clean INTEG1). Decisions posted on PR #3. Amigurumi+pouch (opus2/p0-amigurumi, local c7a8d31e) in 105-suite regression; stocking OPUS2L fixes local, waiting on pet regression.
- 2026-11-02T04:10Z — pet bed K-7/K-8/K-9 pushed (940f70e6, PR #10 commented, 44/44 suites). Stocking OPUS2L fixes committed locally (e07157dc, merged pet), 45-suite regression running; push + PR #11 comment after.
- 2026-11-02T04:45Z — loop 04:28: OPUS2M M-5/M-6 pushed (#7 eba6fb3c), M-2/3/4/8 pushed (#9 5889cc37), M-1/M-7 local (#3, regression). P0-PHOTO-ASSET-REVIEW claimed + built (c056028d local, 116-suite regression). Item 4 mosaic: decision requested (reach-down primitive). Stocking + amigurumi regressions running.
- 2026-11-02T05:08Z — OPUS2M-1/M-7 pushed (#3 8cf4a458, b4merge 80f4b073). OPUS2N-1/2/5 pushed on pet (#10 09122165). Stocking: pet merged + N-1 in shared helper (a859f6fe local, 15-suite run). Tapestry N-1/2/3/4/6 local (17-suite run). Amigurumi/pouch need N-1 after their 105-suite run; photo review 119-suite run.
- 2026-11-02T05:31Z — Stocking OPUS2L+N-1 pushed (#11 a859f6fe, 15/15). Research->PD contract built on opus2/p0-construction-registry (83194fb7 registry, d1ebb27f library-chart engine, 3a11d59a _draft_creative hook; test 5/5: real tournament path, 3 materially different constructions from briefs, holds named). Research findings posted (#3): silhouette_qualifiers for generic forms; no toy arena. Regressions: reg (22), tapn, ami2, photo.
- 2026-11-02T06:34Z — loop 06:28: review OPUS2O read (pet/stocking SHIP; #3 O-1 MED, #9 O-4 MED). O-1 morphology count reader built (#3, 15-suite run). O-4/O-5/O-2 colourwork class fixes built (#9, catalogue unchanged after dropping "one"; 19-suite run). Stocking LOWs O-6/O-7/O-9 built (#11, 15-suite run). Tapestry N pushed (#15 71e26e6f); amigurumi PR #18 opened, merge c0ecc55e in run; registry 8b4076a9 local; photo 45/119.
- 2026-11-02T07:37Z — OPUS2O all pushed: #3 b185b528 (b4merge f4bf34bb), #9 2f9c413d, #11 d3a485a1. #18 merge c0ecc55e pushed. Research->PD registry PR opened (opus2/p0-construction-registry 21d4ceaf, 24/24). Photo review: 46/119 clean before the 2h limit; remaining 73 resumed.
- 2026-11-02T08:40Z — loop 08:37: #15 merged into INTEG1 (#18 retargeted, clean). OPUS2P fixed on #18 (P-1 HIGH children gate, P-2 counted joins, P-3 floor, P-4..P-9) local, 28-suite run. Photo branch: band + guard fixed (5a47cd8e), product_run rerun. Claimed P0-NAME-OBJECT-MISMATCH on #3: head-noun object check, POOL routes unchanged, 14-suite run. Pet+stocking integrated by integrator (52f9f4b5).
